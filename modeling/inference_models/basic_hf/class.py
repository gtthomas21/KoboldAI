from __future__ import annotations

import os
import shutil
import time
from typing import List, Optional, Union

import torch
from transformers.models.auto.modeling_auto import AutoModelForCausalLM

import utils
from logger import logger
from modeling.inference_model import GenerationResult, GenerationSettings
from modeling.inference_models.hf import HFInferenceModel

model_backend_name = "Basic Huggingface"
model_backend_type = "Huggingface"

class model_backend(HFInferenceModel):
    def __init__(self) -> None:
        super().__init__()
        self.model_name = "Basic Huggingface"

        # TODO: These feel weird to be in HFInferenceModel, maybe we could implement
        # them in subclasses?
        self.hf_torch = True
        self.nobreakmodel = True
    
    def _load(self, save_model: bool, initial_load: bool) -> None:
        utils.koboldai_vars.allowsp = False

        if self.model_name == "NeoCustom":
            self.model_name = os.path.basename(os.path.normpath(self.path))
        utils.koboldai_vars.model = self.model_name

        # If we specify a model and it's in the root directory, we need to move
        # it to the models directory (legacy folder structure to new)
        if self.get_local_model_path(legacy=True):
            shutil.move(
                self.get_local_model_path(legacy=True, ignore_existance=True),
                self.get_local_model_path(ignore_existance=True),
            )

        self.init_model_config()

        self.model = AutoModelForCausalLM.from_pretrained(self.get_local_model_path(), low_cpu_mem_usage=True)

        if self.usegpu:
            self.model = self.model.to("cuda")

        self.tokenizer = self._get_tokenizer(self.get_local_model_path())

        self.model.kai_model = self
        utils.koboldai_vars.modeldim = self.model.get_input_embeddings().embedding_dim


    def _raw_generate(
        self,
        prompt_tokens: Union[List[int], torch.Tensor],
        max_new: int,
        gen_settings: GenerationSettings,
        single_line: bool = False,
        batch_count: int = 1,
        seed: Optional[int] = None,
        **kwargs,
    ) -> GenerationResult:
        if not isinstance(prompt_tokens, torch.Tensor):
            gen_in = torch.tensor(prompt_tokens, dtype=torch.long)[None]
        else:
            gen_in = prompt_tokens
        if not self.usegpu:
            gen_in = gen_in.to("cpu")
        else:
            device = self.get_auxilary_device()
            gen_in = gen_in.to(device)

        additional_bad_words_ids = [self.tokenizer.encode("\n")] if single_line else []

        if seed is not None:
            torch.manual_seed(seed)

        with torch.no_grad():
            start_time = time.time()
            genout = self.model.generate(
                gen_in,
                do_sample=True,
                max_length=min(
                    len(prompt_tokens) + max_new, utils.koboldai_vars.max_length
                ),
                repetition_penalty=1.0,
                bad_words_ids=self.badwordsids + additional_bad_words_ids,
                use_cache=True,
                num_return_sequences=batch_count,
            )
        logger.debug(
            "torch_raw_generate: run generator {}s".format(time.time() - start_time)
        )

        return GenerationResult(
            self,
            out_batches=genout,
            prompt=prompt_tokens,
            is_whole_generation=False,
            output_includes_prompt=True,
        )