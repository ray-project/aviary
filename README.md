# Aviary - Study stochastic parrots in the wild

Go on bird watch right now: [🦜🔍 Aviary 🦜🔍](http://aviary.anyscale.com/)

Aviary is an app that lets you interact and deploy large language models (LLMs) in a single place. 
You can compare the outputs of different models directly, rank them by quality,
get a cost and latency estimate, and more. In particular, it offers good support for 
Transformer models hosted on [Hugging Face](http://hf.co) and in many cases also 
supports [DeepSpeed](https://www.deepspeed.ai/) inference acceleration. 

Aviary is built on top of [Ray](https://ray.io) by [Anyscale](https://anyscale.com).

## Table of Contents

* [Getting Help and Filing Bugs / Feature Requests](#Getting-Help-and-Filing-Bugs-/-Feature-Requests)
* [Contributions](#Contributions)
* [Aviary User Guides](#Aviary-User-Guides)
	* [Deploy Aviary ](#Deploy-Aviary)
		* [Query Aviary](#Query-Aviary)
* [Aviary Reference](#Aviary-Reference)
	* [Installing Aviary](#Installing-Aviary)
	* [Running Aviary Frontend locally](#Running-Aviary-Frontend-locally)
		* [Usage stats collection](#Usage-stats-collection)
	* [Using the Aviary CLI](#Using-the-Aviary-CLI)
		* [CLI examples](#CLI-examples)
	* [Aviary Model Registry](#Aviary-Model-Registry)
	* [Contributing](#Contributing)
	* [Running tests](#Running-tests)
	* [Known issues](#Known-issues)
	* [Future plans](#Future-plans)

## Getting Help and Filing Bugs / Feature Requests


We are eager to help you get started with Aviary. You can get help on: 

- Via Slack -- fill in [this form](https://docs.google.com/forms/d/e/1FAIpQLSfAcoiLCHOguOm8e7Jnn-JJdZaCxPGjgVCvFijHB5PLaQLeig/viewform) to sign up. 
- Via [Discuss](https://discuss.ray.io/c/llms-generative-ai/27). 

For bugs or for feature requests, please submit them [here](https://github.com/ray-project/aviary/issues/new).

We have people in both US and European time zones who will help answer your questions. 

# Aviary User Guides

For a video introduction, see the following intro. Note: There have been some minor changes since the video was recorded. The guide below is more up to date. 

[![Watch the video](https://img.youtube.com/vi/WmqPfQOXJ-4/0.jpg)](https://www.youtube.com/watch?v=WmqPfQOXJ-4)

## Deploy Aviary 
From the terminal use the aviary CLI to deploy a model:

```shell
# Deploy the LightGPT model. 
aviary run --model ./models/static_batching/amazon--LightGPT.yaml
```

You can deploy any model in the `models` directory of this repo, 
or define your own model YAML file and run that instead.

### Query Aviary

From the head node, run the following commands. 

```shell
export AVIARY_URL="http://localhost:8000"

# List the available models
aviary models
amazon/LightGPT

# Query the model
aviary query --model amazon/LightGPT --prompt "How do I make fried rice?"
```
```text
amazon/LightGPT:
To make fried rice, start by heating up some oil in a large pan over medium-high
heat. Once the oil is hot, add your desired amount of vegetables and/or meat to the
pan. Cook until they are lightly browned, stirring occasionally. Add any other
desired ingredients such as eggs, cheese, or sauce to the pan. Finally, stir
everything together and cook for another few minutes until all the ingredients are
cooked through. Serve with your favorite sides and enjoy!
```

You can also use `aviary query` with certain LangChain-compatible APIs.
Currently, we support the following APIs:
* openai (`langchain.llms.OpenAIChat`)

```shell
# langchain is an optional dependency
pip install langchain

export OPENAI_API_KEY=...

# Query an Aviary model and OpenAI model
# [PROVIDER]://[MODEL_NAME]
aviary query --model amazon/LightGPT --model openai://gpt-3.5-turbo --prompt "How do I make fried rice?"
```

# Aviary Reference

## Installing Aviary

To install Aviary and its dependencies, run the following command:

```shell
pip install "aviary @ git+https://github.com/ray-project/aviary.git"
```

The default Aviary installation only includes the Aviary API client.

Aviary consists of a backend and a frontend, both of which come with additional
dependencies. To install the dependencies for both frontend and backend for local
development, run the following commands:

```shell
pip install "aviary[frontend,backend] @ git+https://github.com/ray-project/aviary.git"
```

The backend dependencies are heavy weight, and quite large. We only recommend installing
them on a cluster.

## Running Aviary Frontend locally

Aviary consists of two components, a backend and a frontend.
The backend exposes a FastAPI interface running on a Ray cluster,
that allows you to query various LLMs efficiently.
The frontend is a [Gradio](https://gradio.app/) interface that allows you to interact
with the models in the backend through a web interface.
The Gradio app is served using [Ray Serve](https://docs.ray.io/en/latest/serve/index.html).

To run the Aviary frontend locally, you need to set the following environment variable:

```shell
export AVIARY_URL=<hostname of the backend, eg. 'http://localhost:8000'>
```

Once you have set these environment variables, you can run the frontend with the
following command:

```shell
serve run aviary.frontend.app:app
```

To just use the Gradio frontend without Ray Serve, you can start it 
with `python aviary/frontend/app.py`.

If you don't have access to a deployed backend, or would just like to test and develop
the frontend, you can run a mock backend locally by setting `AVIARY_MOCK=True`:

```shell
AVIARY_MOCK=True python aviary/frontend/app.py
```

In any case, the Gradio interface should be accessible at `http://localhost:7860`
in your browser.
If running the frontend yourself is not an option, you can still use 
[our hosted version](http://aviary.anyscale.com/) for your experiments.

### Usage stats collection

Aviary backend collects basic, non-identifiable usage statistics to help us improve the project.
The mechanism for collection is the same as in Ray.
For more information on what is collected and how to opt-out, see the
[Usage Stats Collection](https://docs.ray.io/en/latest/cluster/usage-stats.html) page in
Ray documentation.

## Using the Aviary CLI

Aviary comes with a CLI that allows you to interact with the backend directly, without
using the Gradio frontend.
Installing Aviary as described earlier will install the `aviary` CLI as well.
You can get a list of all available commands by running `aviary --help`.

Currently, `aviary` supports a few basic commands, all of which can be used with the
`--help` flag to get more information:

```shell
# Get a list of all available models in Aviary
aviary models

# Query a model with a list of prompts
aviary query --model <model-name> --prompt <prompt_1> --prompt <prompt_2>

# Run a query on a text file of prompts
aviary query  --model <model-name> --prompt-file <prompt-file>

# Evaluate the quality of responses with GPT-4 for evaluation
aviary evaluate --input-file <query-result-file>

# Start a new model in Aviary from provided configuration
aviary run <model>
```

### CLI examples

#### Listing all available models

```shell
aviary models
```
```text
mosaicml/mpt-7b-instruct
CarperAI/stable-vicuna-13b-delta
databricks/dolly-v2-12b
RWKV/rwkv-raven-14b
mosaicml/mpt-7b-chat
stabilityai/stablelm-tuned-alpha-7b
lmsys/vicuna-13b-delta-v1.1
mosaicml/mpt-7b-storywriter
h2oai/h2ogpt-oasst1-512-12b
OpenAssistant/oasst-sft-7-llama-30b-xor
```

#### Running two models on the same prompt

```shell
aviary query --model mosaicml/mpt-7b-instruct --model RWKV/rwkv-raven-14b \
  --prompt "what is love?"
```
```text
mosaicml/mpt-7b-instruct:
love can be defined as feeling of affection, attraction or ...
RWKV/rwkv-raven-14b:
Love is a feeling of strong affection and care for someone or something...
```

#### Running a batch-query of two prompts on the same model

```shell
aviary query --model mosaicml/mpt-7b-instruct \
  --prompt "what is love?" --prompt "why are we here?"
```

#### Running a query on a text file of prompts

```shell
aviary query --model mosaicml/mpt-7b-instruct --prompt-file prompts.txt
```

#### Evaluating the quality of responses with GPT-4 for evaluation

```shell
 aviary evaluate --input-file aviary-output.json --evaluator gpt-4
```

This will result in a leaderboard-like ranking of responses, but also save the
results to file:

```shell
What is the best indie band of the 90s?
                                              Evaluation results (higher ranks are better)                                               
┏━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Model                    ┃ Rank ┃                                                                                            Response ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ mosaicml/mpt-7b-instruct │ 1    │  The Shins are often considered to be one of the greatest bands from this era, with their album 'Oh │
│                          │      │        Inverted World' being widely regarded as one of the most influential albums in recent memory │
│ RWKV/rwkv-raven-14b      │ 2    │ It's subjective and depends on personal taste. Some people might argue that Nirvana or The Smashing │
│                          │      │                       Pumpkins were the best, while others might prefer Sonic Youth or Dinosaur Jr. │
└──────────────────────────┴──────┴─────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

You can also use the Gradio API directly, by following the instructions
provided in the [Aviary documentation](https://aviary.anyscale.com/?view=api).

## Aviary Model Registry

Aviary allows you to easily add new models by adding a single configuration file.
To learn more about how to customize or add new models, 
see the [Aviary Model Registry](models/README.md).

## Contributing

If you want to help improve or extend the Aviary, please get in touch with us!
You can [reach us via email](mailto:mwk@anyscale.com) for feedback and suggestions,
or [open an issue](https://github.com/ray-project/aviary/issues/new) on GitHub.
Pull requests are also welcome!

We use `pre-commit` hooks to ensure that all code is formatted correctly.
Make sure to `pip install pre-commit` and then run `pre-commit install`.
You can also run `./format` to run the hooks manually.

## Running tests

To run the tests, you need to install the `test` dependencies:

```shell
pip install -e .[test]
```

and then simply run `pytest`:

```shell
pytest .
```

## Known issues

Aviary is still in early development, and there are a few known issues:

* Latency and throughput are not optimized yet. This is due to the fact that we have
chosen to focus on simplicity and readability for the first release. Ray and Ray Serve
are framework-agnostic and Aviary can be easily modified to use FasterTransformer
or other high-performance frameworks. We will continue working on improving this.
* `lmsys/vicuna-13b-delta-v1.1` model sometimes answers to English questions in Mandarin.

## Future plans

* LangChain + LlamaIndex Integration (which will make it much easier to compare open and closed LLMs).
* Better testing.
* Improved documentation.