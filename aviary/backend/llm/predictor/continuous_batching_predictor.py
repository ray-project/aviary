import asyncio
import gc
import time
import traceback
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Tuple

import ray
import ray.exceptions
import ray.util
import torch
import torch.distributed
from ray.air import ScalingConfig

from aviary.backend.llm.continuous.policy import QuotaBasedRequestSelectionPolicy
from aviary.backend.llm.continuous.scheduler import (
    AsyncInferenceScheduler,
    RayTokenizer,
)
from aviary.backend.llm.pipelines.utils import (
    construct_prompts,
)
from aviary.backend.llm.utils import (
    _init_torch_distributed_env_vars_only,
    init_torch_dist_process_group_async,
)
from aviary.backend.server.models import ContinuousBatchingModel, Prompt, Response

from ..utils import get_logger
from .predictor import LLMPredictor, PredictionWorker

try:
    from aviary.backend.llm.continuous.tgi.tgi_worker import TGIRayInferenceWorker
except ImportError as e:
    TGIRayInferenceWorker = e

if TYPE_CHECKING:
    from text_generation_server.models.types import (
        Generation,
    )
    from text_generation_server.pb.generate_pb2 import Request as GenerationRequest

from aviary.backend.llm.continuous.scheduler import Request

logger = get_logger(__name__)


class ContinuousBatchingPredictionWorker(PredictionWorker):
    def warmup(self):
        max_batch_prefill_tokens = self.llm_config.generation.max_batch_prefill_tokens
        max_input_length = self.llm_config.generation.max_input_length
        max_batch_total_tokens = self.llm_config.generation.max_batch_total_tokens
        n_tokens = 0
        requests = []
        while n_tokens < max_batch_prefill_tokens:
            requests.append(
                Request(
                    id=0,
                    inputs="_test " * max_input_length,
                    truncate=min(
                        max_input_length,
                        max_batch_prefill_tokens - n_tokens,
                    ),
                    params={
                        "temperature": 0.9,
                        "top_k": 10,
                        "top_p": 0.9,
                        "typical_p": 0.9,
                        "do_sample": False,
                        "seed": 0,
                        "repetition_penalty": 1.2,
                        "watermark": True,
                        "stop_sequences": [],
                        "ignore_eos_token": False,
                    },
                    max_new_tokens=2,
                )
            )
            n_tokens += max_input_length

        logger.info("Model is warming up...")
        ret = self.generator.warmup(requests, 0, max_batch_total_tokens)
        logger.info("Model finished warming up and is ready to serve requests.")
        return ret

    def process_new_batch(
        self, requests: List["GenerationRequest"], batch_id: int
    ) -> Tuple[List["Generation"], int]:
        if self.current_device:
            torch.cuda.set_device(self.current_device)
        return self.generator.process_new_batch(requests, batch_id)

    def generate_next_token(
        self, batch_ids: List[int]
    ) -> Tuple[List["Generation"], Optional[int]]:
        if self.current_device:
            torch.cuda.set_device(self.current_device)
        return self.generator.generate_next_token(batch_ids)

    def filter_requests(self, batch_id: int, request_ids: List[int]) -> Optional[int]:
        if self.current_device:
            torch.cuda.set_device(self.current_device)
        return self.generator.filter_requests(batch_id, request_ids)

    def get_input_length(self, input_text: str, max_length: int) -> int:
        if self.current_device:
            torch.cuda.set_device(self.current_device)
        return self.generator.get_input_length(input_text, max_length)


# TODO make this non-TGI specific
class ContinuousBatchingPredictor(LLMPredictor):
    def __init__(
        self,
        model_config: Optional[ContinuousBatchingModel],
    ) -> None:
        if isinstance(TGIRayInferenceWorker, Exception):
            raise RuntimeError(
                "ContinuousBatchingPredictor requires text-generation-inference to be installed."
            ) from TGIRayInferenceWorker
        super().__init__(model_config=model_config)
        self.scheduler = None

    @property
    def max_total_tokens(self) -> int:
        """Max input+output tokens in a single request."""
        if not self.model_config:
            return 0
        return self.model_config.generation.max_total_tokens

    @property
    def max_batch_total_tokens(self) -> int:
        if not self.model_config:
            return 0
        return self.model_config.generation.max_batch_total_tokens

    @property
    def max_batch_prefill_tokens(self) -> int:
        if not self.model_config:
            return 0
        return self.model_config.generation.max_batch_prefill_tokens

    @property
    def max_waiting_tokens(self) -> int:
        if not self.model_config:
            return 0
        return self.model_config.generation.max_waiting_tokens

    @property
    def max_input_length(self) -> int:
        if not self.model_config:
            return 0
        return self.model_config.generation.max_input_length

    @property
    def waiting_served_ratio(self) -> float:
        if not self.model_config:
            return 0
        return self.model_config.generation.waiting_served_ratio

    async def _initialize_torch_dist_process_group(
        self, worker_group: List[ray.ObjectRef], **kwargs
    ) -> List[int]:
        return await init_torch_dist_process_group_async(
            worker_group, init_function=_init_torch_distributed_env_vars_only, **kwargs
        )

    async def _start_prediction_workers(
        self, scaling_config: ScalingConfig, remote_prediction_worker_cls: type
    ):
        worker_group = None

        if self.model_config.initialization.full_warmup:
            logger.info(
                f"Starting full warmup with max_batch_prefill_tokens={self.model_config.generation.max_batch_prefill_tokens}, max_input_length={self.model_config.generation.max_input_length}, max_batch_total_tokens={self.model_config.generation.max_batch_total_tokens}"
            )
            logger.warning(
                "Full warmup is intended to be used only for finding the largest feasible max_batch_total_tokens. "
                "It will take a long time and consume a lot of memory. After full warmup is done, note down the "
                "found max_batch_total_tokens value and set it as the new max_batch_total_tokens value in the config. "
                "You may see multiple exceptions in the output - this is normal."
            )
            # Find the largest batch size that can be used for warmup
            final_max_batch_total_tokens = (
                self.model_config.generation.max_batch_total_tokens * 200
            )

            iters = -1
            left = max(
                self.model_config.generation.max_batch_prefill_tokens,
                self.model_config.generation.max_total_tokens,
            )
            right = final_max_batch_total_tokens
            final_max_batch_total_tokens = 0
            last_exception_traceback = None
            while left <= right:
                iters += 1
                mid = (left + right) // 2

                worker_group = None
                gc.collect()

                try:
                    logger.info(f"[{iters}] Testing max_batch_total_tokens={mid}")
                    self.model_config.generation.max_batch_total_tokens = mid
                    worker_group = await super()._start_prediction_workers(
                        scaling_config, remote_prediction_worker_cls
                    )
                    final_max_batch_total_tokens = (
                        mid  # if no exception, this mid value is feasible
                    )
                    left = mid + 1  # explore larger batch size
                except (
                    torch.cuda.OutOfMemoryError,
                    AssertionError,
                    ray.exceptions.RayActorError,
                    RuntimeError,
                ):
                    right = mid - 1  # explore smaller batch size
                    last_exception_traceback = traceback.format_exc()
                    logger.warning(last_exception_traceback)

            if not final_max_batch_total_tokens:
                raise ValueError(
                    f"Could not find a feasible max_batch_total_tokens value. Please check your config and try again. Last exception:\n{last_exception_traceback}"
                )
            final_max_batch_total_tokens = int(
                final_max_batch_total_tokens * 0.95
            )  # leave a little leeway
            logger.info(
                f"Full warmup done in {iters} iterations. Final max_batch_total_tokens: {final_max_batch_total_tokens}."
            )
            self.model_config.generation.max_batch_total_tokens = (
                final_max_batch_total_tokens
            )

        if worker_group is None:
            worker_group = await super()._start_prediction_workers(
                scaling_config, remote_prediction_worker_cls
            )

        assert worker_group
        return worker_group

    async def _create_worker_group(
        self,
        scaling_config: ScalingConfig,
        pg_timeout_s: float = 600,
        prediction_worker_cls=ContinuousBatchingPredictionWorker,
    ) -> List[ray.ObjectRef]:
        assert self.model_config
        assert scaling_config.placement_strategy == "STRICT_PACK"

        worker_group = await super()._create_worker_group(
            scaling_config, pg_timeout_s, prediction_worker_cls=prediction_worker_cls
        )

        self.scheduler = AsyncInferenceScheduler(
            tokenizer=RayTokenizer(worker_group=worker_group),
            inference_worker_loader=lambda: TGIRayInferenceWorker(
                worker_group=worker_group
            ),
            request_selection_policy=QuotaBasedRequestSelectionPolicy(
                max_batch_total_tokens=self.max_batch_total_tokens,
                max_waiting_tokens=self.max_waiting_tokens,
                max_batch_prefill_tokens=self.max_batch_prefill_tokens,
                waiting_served_ratio=self.waiting_served_ratio,
            ),
            request_queue=asyncio.Queue(),
        )

        return worker_group

    def process_request(
        self, prompt: str, max_new_tokens: int, sampling_params: Dict[str, Any]
    ):
        # TODO improve error message
        assert max_new_tokens + self.max_input_length <= self.max_total_tokens
        return self.scheduler.process_request(
            prompt,
            sampling_params,
            max_new_tokens=max_new_tokens,
            max_length=self.max_input_length,
        )

    async def _stream_async(
        self,
        prompts: List[Prompt],
        *,
        timeout_s: float = 60,
        start_timestamp: Optional[float] = None,
        **kwargs,
    ) -> Iterator[List[Response]]:
        """Generate text for a list of prompts.

        Args:
            prompts (List[Prompt]): Batch of prompts to generate text from.
            timeout_s (float, optional): Timeout for the generation. Defaults
                to 60. Ignored if start_timestamp is None.
            start_timestamp (Optional[float], optional): Timestamp of when the
                batch was created. Defaults to None. If set, will early stop
                the generation.

        Returns:
            A list of generated texts.
        """
        model_config = self.model_config
        assert len(prompts) == 1

        prompt = prompts[0]
        prompt_text = construct_prompts(
            prompt,
            prompt_format=self.model_config.generation.prompt_format,
        )[0]

        stopping_sequences = (
            prompt.stopping_sequences
            if prompt.stopping_sequences is not None
            else model_config.generation.stopping_sequences
        )
        generate_kwargs = (
            prompt.parameters
            if prompt.parameters is not None
            else model_config.generation.generate_kwargs
        )
        max_new_tokens = max(generate_kwargs.get("max_new_tokens", 512), 512)

        result = self.process_request(
            prompt_text,
            max_new_tokens=max_new_tokens,
            sampling_params={
                **generate_kwargs,
                "use_prompt_format": prompt.use_prompt_format,
                "stopping_sequences": stopping_sequences,
            },
        )
        request_id = result.id
        logger.info(f"Starting stream for {request_id}, prompt_text:\n{prompt_text}")
        generated_text = []
        try:
            start_time = time.monotonic()
            async for text in result:
                # TODO maybe make the Scheduler/TokenStream return a Response directly
                generated_text.append(text)
                yield [
                    Response(
                        generated_text=text,
                        num_generated_tokens=1,
                        num_generated_tokens_batch=1,
                        num_input_tokens=result.num_input_tokens,
                        num_input_tokens_batch=result.num_input_tokens,
                        preprocessing_time=0,
                        generation_time=time.monotonic() - start_time,
                    )
                ]
                start_time = time.monotonic()
            yield [StopIteration]
        except (Exception, asyncio.CancelledError):
            logger.info(f"Stream cancelled for {request_id}")
            self.scheduler.cancel_request(request_id)
            raise
        # Debug code
        # generated_text = (result._generated_text or "").strip()
        # generated_text_from_tokens = "".join(generated_text).strip()
        # if generated_text == generated_text_from_tokens:
        #     logger.info(
        #         f"Stream finished for {request_id}, final response:\n{generated_text}"
        #     )
        # else:
        #     logger.error(
        #         f"ERROR: Stream finished for {request_id}, final response:\n{generated_text}\ndoesn't match\n {generated_text_from_tokens}"
        #     )
