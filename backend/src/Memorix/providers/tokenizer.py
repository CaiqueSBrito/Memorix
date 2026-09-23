from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("neuralmind/bert-base-portuguese-cased", use_fast=True)