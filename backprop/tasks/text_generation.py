from typing import List, Tuple, Union, Dict
from backprop.models import GPT2Large, T5QASummaryEmotion, BaseModel, T5
from .base import Task

import requests

DEFAULT_LOCAL_MODEL = GPT2Large

LOCAL_MODELS = {
    "gpt2": DEFAULT_LOCAL_MODEL,
    "t5-base-qa-summary-emotion": T5QASummaryEmotion,
    "t5": T5
}

DEFAULT_API_MODEL = "gpt2-large"

FINETUNABLE_MODELS = ["t5", "t5-base-qa-summary-emotion"]

API_MODELS = ["gpt2-large", "t5-base-qa-summary-emotion"]

class TextGeneration(Task):
    """
    Task for text generation.

    Attributes:
        model:
            1. Name of the model on Backprop's generation endpoint (gpt2-large, t5-base-qa-summary-emotion or your own uploaded model)
            2. Officially supported local models (gpt2, t5-base-qa-summary-emotion).
            3. Model object/class that inherits from backprop's TextGenerationModel
            4. Path/name of saved Backprop model
        local (optional): Run locally. Defaults to False
        api_key (optional): Backprop API key for non-local inference
        device (optional): Device to run inference on. Defaults to "cuda" if available.
    """
    def __init__(self, model: Union[str, BaseModel] = None,
                local: bool = False, api_key: str = None, device: str = None):

        super().__init__(model, local=local, api_key=api_key, device=device,
                        local_models=LOCAL_MODELS, api_models=API_MODELS,
                        default_local_model=DEFAULT_LOCAL_MODEL,
                        default_api_model=DEFAULT_API_MODEL)

    
    def __call__(self, text: Union[str, List[str]], min_length: int = None, max_length: int = None, temperature: float = None,
                top_k: int = None, top_p: float = None, repetition_penalty: float = None, length_penalty: float = None,
                num_beams: int = None, num_generations: int = None, do_sample: bool = None):
        """Generates text to continue from the given input.

        Args:
            input_text (string): Text from which the model will begin generating.
            min_length (int): Minimum number of tokens to generate (1 token ~ 1 word).
            max_length (int): Maximum number of tokens to generate (1 token ~ 1 word).
            temperature (float): Value that alters the randomness of generation (0.0 is no randomness, higher values introduce randomness. 0.5 - 0.7 is a good starting point).
            top_k (int): Only choose from the top_k tokens when generating (0 is no limit). 
            top_p (float): Only choose from the top tokens with combined probability greater than top_p.
            repetition_penalty (float): Penalty to be applied to tokens present in the input_text and
                tokens already generated in the sequence (>1 discourages repetition while <1 encourages).
            length_penalty (float): Penalty applied to overall sequence length. Set >1 for longer sequences,
                or <1 for shorter ones. 
            num_beams (int): Number of beams to be used in beam search. Does a number of generations to pick the best one. (1: no beam search)
            num_generations (int): How many times to run generation. Results are returned as a list. 
            do_sample (bool): Whether or not sampling strategies (temperature, top_k, top_p) should be used.

        Example::

            import backprop

            tg = backprop.TextGeneration()
            tg("Geralt knew the sings, the monster was a", min_length=20, max_length=50, temperature=0.7)
            > "Geralt knew the sings, the monster was a real danger, and he was the only one in the village who knew how to defend himself."
        """
        params = [("text", text), ("min_length", min_length), ("max_length", max_length),
                ("temperature", temperature), ("top_k", top_k), ("top_p", top_p),
                ("repetition_penalty", repetition_penalty), ("length_penalty", length_penalty),
                ("num_beams", num_beams), ("num_generations", num_generations),
                ("do_sample", do_sample)]
        
        # Ignore None to let the model decide optimal values
        task_input = {k: v for k, v in params if v != None}
        if self.local:
            return self.model(task_input, task="text-generation")
        else:
            task_input["model"] = self.model 

            res = requests.post("https://api.backprop.co/text-generation", json=task_input,
                                headers={"x-api-key": self.api_key}).json()

            if res.get("message"):
                raise Exception(f"Failed to make API request: {res['message']}")

            return res["output"]

    def finetune(self, params: Dict, *args, **kwargs):
        """
        Passes the args and kwargs to the model's finetune method.
        
        Args:
            params: dictionary of 'input_text' and 'output_text' lists.
        """

        if not "input_text" in params:
            print("Params requires key: 'input_text' (list of inputs)")
            return
        if not "output_text" in params:
            print("Params requires key: 'output_text' (list of outputs)")
            return

        try:
            return self.model.finetune(params=params, task="text-generation", *args, **kwargs)
        except NotImplementedError:
            raise NotImplementedError(f"This model does not support finetuning, try: {', '.join(FINETUNABLE_MODELS)}")