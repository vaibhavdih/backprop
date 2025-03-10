from typing import List, Tuple
from transformers import AutoModelForPreTraining, AutoTokenizer, \
    AutoModelForSequenceClassification, AdamW
from torch.utils.data import DataLoader
from sentence_transformers import SentenceTransformer
from functools import partial
import os

import torch
import torch.nn.functional as F
import pytorch_lightning as pl
from pytorch_lightning.callbacks.early_stopping import EarlyStopping
from pytorch_lightning.utilities.memory import garbage_collection_cuda

class BaseModel:
    """
    The base class for a model.
    
    Attributes:
        model: Your model that takes some args, kwargs and returns an output.
            Must be callable.
    """
    def __init__(self, model, name: str = None, description: str = None, tasks: List[str] = None):
        self.model = model
        self.name = name or "base-model"
        self.description = description or "This is the base description. Change me."
        self.tasks = tasks or [] # Supports no tasks

    def __call__(self, *args, **kwargs):
        return self.model(*args, **kwargs)

    def finetune(self, *args, **kwargs):
        raise NotImplementedError("This model does not support finetuning")

    def to(self, device):
        self.model.to(device)
        self._model_device = device

    # def set_name(self, name: str):


class Finetunable(pl.LightningModule):
    """
    Makes a model easily finetunable.
    """
    def __init__(self):
        pl.LightningModule.__init__(self)

        self.batch_size = 1

    def finetune(self, dataset, validation_split: float = 0.15, epochs: int = 20, batch_size: int = None,
                optimal_batch_size: int = None, early_stopping: bool = True, trainer = None):
        self.batch_size = batch_size or 1

        if not torch.cuda.is_available():
            raise Exception("You need a cuda capable (Nvidia) GPU for finetuning")
        
        len_train = int(len(dataset) * (1 - validation_split))
        len_valid = len(dataset) - len_train
        dataset_train, dataset_valid = torch.utils.data.random_split(dataset, [len_train, len_valid])

        self.dataset_train = dataset_train
        self.dataset_valid = dataset_valid

        if batch_size == None:
            # Find batch size
            temp_trainer = pl.Trainer(auto_scale_batch_size="power", gpus=-1)
            print("Finding the optimal batch size...")
            temp_trainer.tune(self)

            # Ensure that memory gets cleared
            del self.trainer
            del temp_trainer
            garbage_collection_cuda()

        trainer_kwargs = {}
        
        if optimal_batch_size:
            # Don't go over
            batch_size = min(self.batch_size, optimal_batch_size)
            accumulate_grad_batches = max(1, int(optimal_batch_size / batch_size))
            trainer_kwargs["accumulate_grad_batches"] = accumulate_grad_batches
        
        if early_stopping:
            # Stop when val loss stops improving
            early_stopping = EarlyStopping(monitor="val_loss", patience=1)
            trainer_kwargs["callbacks"] = [early_stopping]

        if not trainer:
            trainer = pl.Trainer(gpus=-1, max_epochs=epochs, checkpoint_callback=False,
                logger=False, **trainer_kwargs)

        self.model.train()
        trainer.fit(self)

        del self.dataset_train
        del self.dataset_valid
        del self.trainer

        # For some reason the model can end up on CPU after training
        self.to(self._model_device)
        self.model.eval()
        print("Training finished! Save your model for later with backprop.save or upload it with backprop.upload")

    def train_dataloader(self):
        return DataLoader(self.dataset_train,
            batch_size=self.batch_size,
            num_workers=os.cpu_count() or 0)

    def val_dataloader(self):
        return DataLoader(self.dataset_valid,
            batch_size=self.batch_size,
            num_workers=os.cpu_count() or 0)
    
    def configure_optimizers(self):
        raise NotImplementedError("configure_optimizers must be implemented")

    def training_step(self, batch, batch_idx):
        raise NotImplementedError("training_step must be implemented")

    def validation_step(self, batch, batch_idx):
        raise NotImplementedError("validation_step must be implemented")



class PathModel(BaseModel):
    """
    Class for models which are initialised from a path.

    Attributes:
        model_path: Path to the model
        init_model: Callable to initialise model from path
        tokenizer_path (optional): Path to the tokenizer
        init_tokenizer (optional): Callable to initialise tokenizer from path
        device (optional): Device for inference. Defaults to "cuda" if available.
    """
    def __init__(self, model_path, init_model, tokenizer_path=None,
                init_tokenizer=None, device=None):
        self.init_model = init_model
        self.init_tokenizer = init_tokenizer
        self.model_path = model_path
        self.tokenizer_path = tokenizer_path
        self._model_device = device

        if self._model_device is None:
            self._model_device = "cuda" if torch.cuda.is_available() else "cpu"

        # Initialise
        self.model = self.init_model(model_path).eval().to(self._model_device)

        # Not all models need tokenizers
        if self.tokenizer_path:
            self.tokenizer = self.init_tokenizer(self.tokenizer_path)
        

    def __call__(self, *args, **kwargs):
        return self.model(*args, **kwargs)


class HuggingModel(PathModel):
    """
    Class for models which are initialised from a local path or huggingface

    Attributes:
        model_path: Local or huggingface.co path to the model
        init_model: Callable to initialise model from path
            Defaults to AutoModelForPreTraining from huggingface
        tokenizer_path (optional): Path to the tokenizer
        init_tokenizer (optional): Callable to initialise tokenizer from path
            Defaults to AutoTokenizer from huggingface.
        device (optional): Device for inference. Defaults to "cuda" if available.
    """
    def __init__(self, model_path, tokenizer_path=None,
                model_class=AutoModelForPreTraining,
                tokenizer_class=AutoTokenizer, device=None):
        # Usually the same
        if not tokenizer_path:
            tokenizer_path = model_path

        # Object was made with init = False
        if hasattr(self, "initialised"):
            model_path = self.model_path
            tokenizer_path = self.tokenizer_path
            init_model = self.init_model
            init_tokenizer = self.init_tokenizer
            device = self._model_device
        else:
            init_model = model_class.from_pretrained
            init_tokenizer = tokenizer_class.from_pretrained

        return PathModel.__init__(self, model_path, tokenizer_path=tokenizer_path,
                                init_model=init_model,
                                init_tokenizer=init_tokenizer,
                                device=device)


class TextVectorisationModel(PathModel, Finetunable):
    """
    Class for models which are initialised from a local path or Sentence Transformers

    Attributes:
        model_path: Local, sentence transformers or huggingface.co path to the model
        init_model: Callable to initialise model from path
            Defaults to SentenceTransformer
        device (optional): Device for inference. Defaults to "cuda" if available.
    """
    def __init__(self, model_path, init_model=SentenceTransformer,
                device=None):
        Finetunable.__init__(self)

        init_model = partial(init_model, device=device)

        PathModel.__init__(self, model_path,
                                init_model=init_model,
                                device=device)

        self.batch_size = 1
        self.tasks = ["text-vectorisation"]
        self.description = "This is a text vectorisation model"
        self.name = "text-vec-model"


    def __call__(self, *args, **kwargs):
        return self.vectorise(*args, **kwargs)

    @torch.no_grad()
    def vectorise(self, *args, **kwargs):
        return self.model.encode(*args, **kwargs)

    def training_step(self, batch, batch_idx):
        out1 = self.model.forward({"input_ids": batch["input_ids1"], "attention_mask": batch["attention_mask1"]})["sentence_embedding"]
        out2 = self.model.forward({"input_ids": batch["input_ids2"], "attention_mask": batch["attention_mask2"]})["sentence_embedding"]
        scores = batch["scores"]

        loss = torch.cosine_similarity(out1, out2)
        loss = F.mse_loss(loss, scores.view(-1))
        
        self.log("train_loss", loss, on_step=True, on_epoch=True, prog_bar=True, logger=True)
        return loss
    
    def validation_step(self, batch, batch_idx):
        out1 = self.model.forward({"input_ids": batch["input_ids1"], "attention_mask": batch["attention_mask1"]})["sentence_embedding"]
        out2 = self.model.forward({"input_ids": batch["input_ids2"], "attention_mask": batch["attention_mask2"]})["sentence_embedding"]
        scores = batch["scores"]

        loss = torch.cosine_similarity(out1, out2)
        loss = F.mse_loss(loss, scores.view(-1))
        self.log("val_loss", loss, prog_bar=True, on_epoch=True, logger=True)
        return loss

    def configure_optimizers(self):
        return AdamW(params=self.model.parameters(), lr=2e-5, eps=1e-6, correct_bias=False)

    def encode(self, row, max_input_length):
        inp = self.encode_input(row[0], max_length=max_input_length)
        out = self.encode_output(row[1])

        row = {**inp, **out}
        return row

    def encode_input(self, text_pair, max_length=128):
        text1, text2 = text_pair
        tokens1 = self.model.tokenizer(text1, truncation=True, max_length=max_length, padding="max_length", return_tensors="pt")
        tokens2 = self.model.tokenizer(text2, truncation=True, max_length=max_length, padding="max_length", return_tensors="pt")
        return {"input_ids1": tokens1.input_ids[0], "attention_mask1": tokens1.attention_mask[0],
                "input_ids2": tokens2.input_ids[0], "attention_mask2": tokens2.attention_mask[0]}

    def encode_output(self, similarity_score):
        return {"scores": torch.tensor([similarity_score], dtype=torch.float32)}

    def finetune(self, text_pairs: List[Tuple[str, str]], similarity_scores: List[float],
                max_input_length=64,
                validation_split: float = 0.15, epochs: int = 20,
                batch_size: int = None, early_stopping: bool = True,
                trainer: pl.Trainer = None):
        """
        Finetunes the model for the text-vectorisation task.
        
        Note:
            text_pairs and similarity_scores must have matching ordering (item 1 of text_pairs must match item 1 of similarity_scores)

        Args:
            text_pairs: List of text pairs that are to be compares (must match output ordering)
            similarity_scores: List of floats between 0 and 1 that score the similarity of the pairs (must match text pairs ordering)
            max_input_length: Maximum number of tokens (1 token ~ 1 word) in text. Anything higher will be truncated. Max 512.
            validation_split: Float between 0 and 1 that determines what percentage of the data to use for validation
            epochs: Integer that specifies how many iterations of training to do
            batch_size: Leave as None to determine the batch size automatically
            early_stopping: Boolean that determines whether to automatically stop when validation loss stops improving
            trainer: Your custom pytorch_lightning trainer

        Example::

            import backprop
            
            # Initialise a text vectorisation model
            model = backprop.models.DistiluseBaseMultilingualCasedV2()

            # Any text works as training data
            inp = [("hello there", "hi there"), ("how are you", "where is my wallet?")]
            scores = [1.0, 0.0]

            # Finetune
            model.finetune(inp, scores)
        """

        assert len(text_pairs) == len(similarity_scores), "Input list must match the output list"
        OPTIMAL_BATCH_SIZE = 128

        print("Processing data...")
        dataset = zip(text_pairs, similarity_scores)
        dataset = [self.encode(r, max_input_length) for r in dataset]

        Finetunable.finetune(self, dataset)


class TextGenerationModel(HuggingModel):
    """
    Class for models which are initialised from a local path or Sentence Transformers

    Attributes:
        *args and **kwargs are passed to HuggingModel's __init__
    """
    def generate(self, text, **kwargs):
        """
        Generate according to the model's generate method.
        """
        # Get and remove do_sample or set to False
        do_sample = kwargs.pop("do_sample", None) or False
        params = ["temperature", "top_k", "top_p", "repetition_penalty",
                    "length_penalty", "num_beams", "num_return_sequences", "num_generations"]

        # If params are changed, we want to sample
        for param in params:
            if param in kwargs.keys() and kwargs[param] != None:
                do_sample = True
                break

        if "temperature" in kwargs:
            # No sampling
            if kwargs["temperature"] == 0.0:
                do_sample = False
                del kwargs["temperature"]

        # Override, name correctly
        if "num_generations" in kwargs:
            if kwargs["num_generations"] != None:
                kwargs["num_return_sequences"] = kwargs["num_generations"]
                
            del kwargs["num_generations"]

        is_list = False
        if isinstance(text, list):
            is_list = True

        if not is_list:
            text = [text]

        all_tokens = []
        for text in text:
            features = self.tokenizer(text, return_tensors="pt")

            for k, v in features.items():
                features[k] = v.to(self._model_device)

            with torch.no_grad():
                tokens = self.model.generate(do_sample=do_sample,
                                            **features, **kwargs)

            all_tokens.append(tokens)
            
        value = []
        for tokens in all_tokens:
            value.append([self.tokenizer.decode(tokens, skip_special_tokens=True)
                    for tokens in tokens])
        
        output = value

        # Unwrap generation list
        if kwargs.get("num_return_sequences", 1) == 1:
            output_unwrapped = []
            for value in output:
                output_unwrapped.append(value[0])

            output = output_unwrapped
        
        # Return single item
        if not is_list:
            output = output[0]

        return output


class ClassificationModel(HuggingModel):
    """
    Class for classification models which are initialised from a local path or huggingface

    Attributes:
        model_path: Local or huggingface.co path to the model
        tokenizer_path (optional): Path to the tokenizer
        model_class (optional): Callable to initialise model from path
            Defaults to AutoModelForSequenceClassification from huggingface
        tokenizer_class (optional): Callable to initialise tokenizer from path
            Defaults to AutoTokenizer from huggingface.
        device (optional): Device for inference. Defaults to "cuda" if available.
    """
    def __init__(self, model_path, tokenizer_path=None,
                model_class=AutoModelForSequenceClassification,
                tokenizer_class=AutoTokenizer, device=None):
        return super().__init__(model_path, tokenizer_path=tokenizer_path,
                    model_class=model_class, tokenizer_class=tokenizer_class,
                    device=device)

    def calculate_probability(self, text, label, device):
        hypothesis = f"This example is {label}."
        features = self.tokenizer.encode(text, hypothesis, return_tensors="pt",
                                    truncation=True).to(self._model_device)
        logits = self.model(features)[0]
        entail_contradiction_logits = logits[:, [0, 2]]
        probs = entail_contradiction_logits.softmax(dim=1)
        prob_label_is_true = probs[:, 1]
        return prob_label_is_true.item()


    def classify(self, text, labels):
        """
        Classifies text, given a set of labels.
        """
        if isinstance(text, list):
            # Must have a consistent amount of examples
            assert(len(text) == len(labels))
            # TODO: implement proper batching
            results_list = []
            for text, labels in zip(text, labels):
                results = {}
                for label in labels:
                    results[label] = self.calculate_probability(text, label, self._model_device)

                results_list.append(results)

            return results_list
        else:
            results = {}
            for label in labels:
                results[label] = self.calculate_probability(
                    text, label, self._model_device)

            return results