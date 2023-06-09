import json
import os
import warnings
from typing import Any, Dict, Iterator, List, Optional, Union

import requests

from aviary.api.utils import (
    AviaryBackend,
    BackendError,
    _convert_to_aviary_format,
    _get_langchain_model,
    _is_aviary_model,
    _supports_batching,
    assert_has_backend,
)
from aviary.common.constants import DEFAULT_API_VERSION, TIMEOUT

__all__ = [
    "models",
    "metadata",
    "completions",
    "batch_completions",
    "run",
    "get_aviary_backend",
    "stream",
]


def get_aviary_backend():
    """
    Establishes a connection to the Aviary backed after establishing
    the information using environmental variables.
    If the AVIARY_MOCK environmental variable is set, then a mock backend is used.

    For direct connection to the aviary backend (e.g. running on the same cluster),
    no AVIARY_TOKEN is required. Otherwise, the AVIARY_URL and AVIARY_TOKEN environment
    variables are required.

    Returns:
        backend: An instance of the Backend class.
    """
    aviary_url = os.getenv("AVIARY_URL")
    assert aviary_url, "AVIARY_URL must be set"

    aviary_token = os.getenv("AVIARY_TOKEN", "")

    bearer = f"Bearer {aviary_token}" if aviary_token else ""
    aviary_url += "/" if not aviary_url.endswith("/") else ""

    print("Connecting to Aviary backend at: ", aviary_url)
    return AviaryBackend(aviary_url, bearer)


def models(version: str = DEFAULT_API_VERSION) -> List[str]:
    """List available models"""
    backend = get_aviary_backend()
    request_url = backend.backend_url + "-/routes"
    response = requests.get(request_url, headers=backend.header, timeout=TIMEOUT)
    try:
        result = response.json()
    except requests.JSONDecodeError as e:
        raise BackendError(
            f"Error decoding JSON from {request_url}. Text response: {response.text}",
            response=response,
        ) from e
    result = sorted(
        [k.lstrip("/").replace("--", "/") for k in result.keys() if "--" in k]
    )
    return result


def metadata(
    model_id: str, version: str = DEFAULT_API_VERSION
) -> Dict[str, Dict[str, Any]]:
    """Get model metadata"""
    backend = get_aviary_backend()
    url = backend.backend_url + model_id.replace("/", "--") + "/" + version + "metadata"
    response = requests.get(url, headers=backend.header, timeout=TIMEOUT)
    try:
        result = response.json()
    except requests.JSONDecodeError as e:
        raise BackendError(
            f"Error decoding JSON from {url}. Text response: {response.text}",
            response=response,
        ) from e
    return result


def completions(
    model: str,
    prompt: str,
    use_prompt_format: bool = True,
    version: str = DEFAULT_API_VERSION,
    **kwargs,
) -> Dict[str, Union[str, float, int]]:
    """Get completions from Aviary models."""

    if _is_aviary_model(model):
        backend = get_aviary_backend()
        url = backend.backend_url + model.replace("/", "--") + "/" + version + "query"
        response = requests.post(
            url,
            headers=backend.header,
            json={"prompt": prompt, "use_prompt_format": use_prompt_format, **kwargs},
            timeout=TIMEOUT,
        )
        try:
            return response.json()
        except requests.JSONDecodeError as e:
            raise BackendError(
                f"Error decoding JSON from {url}. Text response: {response.text}",
                response=response,
            ) from e
    llm = _get_langchain_model(model)
    return llm.predict(prompt)


def query(
    model: str,
    prompt: str,
    use_prompt_format: bool = True,
    version: str = DEFAULT_API_VERSION,
    **kwargs,
) -> Dict[str, Union[str, float, int]]:
    warnings.warn(
        "'query' is deprecated, please use 'completions' instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return completions(model, prompt, use_prompt_format, version)


def batch_completions(
    model: str,
    prompts: List[str],
    use_prompt_format: Optional[List[bool]] = None,
    version: str = DEFAULT_API_VERSION,
    kwargs: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Union[str, float, int]]]:
    """Get batch completions from Aviary models."""

    if not kwargs:
        kwargs = [{}] * len(prompts)

    if not use_prompt_format:
        use_prompt_format = [True] * len(prompts)

    if _is_aviary_model(model):
        backend = get_aviary_backend()
        url = backend.backend_url + model.replace("/", "--") + "/" + version + "batch"
        response = requests.post(
            url,
            headers=backend.header,
            json=[
                {"prompt": prompt, "use_prompt_format": use_format, **kwarg}
                for prompt, use_format, kwarg in zip(prompts, use_prompt_format, kwargs)
            ],
            timeout=TIMEOUT,
        )
        try:
            return response.json()
        except requests.JSONDecodeError as e:
            raise BackendError(
                f"Error decoding JSON from {url}. Text response: {response.text}",
                response=response,
            ) from e
    else:
        llm = _get_langchain_model(model)
        if _supports_batching(model):
            result = llm.generate(prompts)
            converted = _convert_to_aviary_format(model, result)
        else:
            result = [{"generated_text": llm.predict(prompt)} for prompt in prompts]
            converted = result
        return converted


def stream(
    model: str,
    prompt: str,
    use_prompt_format: bool = True,
    version: str = DEFAULT_API_VERSION,
    **kwargs,
) -> Iterator[Dict[str, Union[str, float, int]]]:
    """Query Aviary and stream response"""
    if _is_aviary_model(model):
        backend = get_aviary_backend()
        url = backend.backend_url + model.replace("/", "--") + "/" + version + "stream"
        response = requests.post(
            url,
            headers=backend.header,
            json={"prompt": prompt, "use_prompt_format": use_prompt_format, **kwargs},
            timeout=TIMEOUT,
            stream=True,
        )
        chunk = ""
        try:
            for chunk in response.iter_lines(chunk_size=None, decode_unicode=True):
                chunk = chunk.strip()
                if not chunk:
                    continue
                data = json.loads(chunk)
                if "error" in data:
                    raise BackendError(data["error"], response=response)
                yield data
        except ConnectionError as e:
            raise BackendError(str(e) + "\n" + chunk, response=response) from e
    else:
        # TODO implement streaming for langchain models
        raise RuntimeError("Streaming is currently only supported for aviary models")


def batch_query(
    model: str,
    prompts: List[str],
    use_prompt_format: Optional[List[bool]] = None,
    version: str = DEFAULT_API_VERSION,
    kwargs: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Union[str, float, int]]]:
    warnings.warn(
        "'batch_query' is deprecated, please use " "'batch_completions' instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return batch_completions(model, prompts, use_prompt_format, version, kwargs)


def run(*model: str) -> None:
    """Run Aviary on the local ray cluster

    NOTE: This only works if you are running this command
    on the Ray or Anyscale cluster directly. It does not
    work from a general machine which only has the url and token
    for a model.
    """
    assert_has_backend()
    from aviary.backend.server.run import run

    run(*model)
