import os

import requests


class GPT:
    """A simple wrapper around the OpenAI API for evaluating GPT models."""

    def __init__(self, model_version="gpt-4", temperature=0.9, max_tokens=2048):
        api_key = os.getenv("GPT4_API_KEY")
        assert api_key, "Please set the GPT4_API_KEY environment variable"
        self.__api_key = os.getenv("GPT4_API_KEY")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model = model_version

    def evaluate_results(self, prompt, results):
        """Evaluate a list of results generated by several models on a single prompt."""
        for result in results:
            result.pop("stats", None)

        gpt_messages = [
            {
                "role": "system",
                "content": (
                    """You are an assistant tasked with ranking responses in 
                    order of quality, creating a leaderboard of all models.
                    The best model has rank 1, the second best has rank 2, etc.
                    You have to assess the quality of the responses, and rank them."""
                ),
            },
            {
                "role": "user",
                "content": (
                    f"""You are given a prompt and a list of responses
                    from several models in Python dictionary format. 
                    Specifically, the format of the results is as follows:
                    
                    'model': <model-name>, 'result': <model-output>
                    
                    Your job is to "rank" the responses in order of quality, (not by
                    the order in which they were generated).
                    
                    The prompt is: {prompt}
                    The responses are: {results}
                    
                    Please rank the responses by quality, and return a list of the model
                    names and ranks, i.e produce the following output:
                    
                    'model': <model-name>, 'rank': <model-rank>
                    
                    Only output this format, and nothing else. Your response must
                    be a valid Python dictionary.
                    Think step by step and give me this quality ranking.
                    """
                ),
            },
        ]
        return self.generate(gpt_messages)

    def generate(self, messages):
        data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.__api_key}",
        }
        resp = requests.post(
            url="https://api.openai.com/v1/chat/completions", json=data, headers=headers
        )

        if not resp.ok:
            raise RuntimeError(f"Failed to generate: {resp.reason}")

        return resp.json()["choices"][0]["message"]["content"]
