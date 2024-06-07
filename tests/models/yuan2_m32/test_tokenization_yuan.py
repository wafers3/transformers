# coding=utf-8


import json
import os
import unittest

from transformers import AddedToken, YuanTokenizer, YuanTokenizerFast
from transformers.models.yuan2_m32.tokenization_yuan import VOCAB_FILES_NAMES, bytes_to_unicode
from transformers.testing_utils import require_tokenizers, slow

from ...test_tokenization_common import TokenizerTesterMixin


@require_tokenizers
class YuanTokenizationTest(TokenizerTesterMixin, unittest.TestCase):
    from_pretrained_id = "Yuan/yuan-tokenizer"
    tokenizer_class = YuanTokenizer
    rust_tokenizer_class = YuanTokenizerFast
    test_slow_tokenizer = True
    test_rust_tokenizer = True
    space_between_special_tokens = False
    from_pretrained_kwargs = None
    test_seq2seq = False

    def setUp(self):
        super().setUp()

        # this make sure the vocabuary is complete at the byte level.
        vocab = list(bytes_to_unicode().values())
        # the vocabulary, note:
        # - `"\u0120n"`, `"\u0120lowest"`, `"\u0120newer"`, and `"\u0120wider"` are ineffective, because there are
        #   not in the merges.
        # - `"01"` is ineffective, because the merge is ineffective due to pretokenization.
        vocab.extend(
            [
                "\u0120l",
                "\u0120n",
                "\u0120lo",
                "\u0120low",
                "er",
                "\u0120lowest",
                "\u0120newer",
                "\u0120wider",
                "01",
                ";}",
                ";}\u010a",
                "\u00cf\u0135",
                "\u0120#",
                "##",
            ]
        )

        vocab_tokens = dict(zip(vocab, range(len(vocab))))

        # note: `"0 1"` is in the merges, but the pretokenization rules render it ineffective
        merges = [
            "#version: 0.2",
            "\u0120 l",
            "\u0120l o",
            "\u0120lo w",
            "e r",
            "0 1",
            "; }",
            ";} \u010a",
            "\u00cf \u0135",
            "\u0120 #",
            "# #",
        ]

        self.special_tokens_map = {"eos_token": "<|endoftext|>"}

        self.vocab_file = os.path.join(self.tmpdirname, VOCAB_FILES_NAMES["vocab_file"])
        self.merges_file = os.path.join(self.tmpdirname, VOCAB_FILES_NAMES["merges_file"])
        with open(self.vocab_file, "w", encoding="utf-8") as fp:
            fp.write(json.dumps(vocab_tokens) + "\n")
        with open(self.merges_file, "w", encoding="utf-8") as fp:
            fp.write("\n".join(merges))

    def get_tokenizer(self, **kwargs):
        kwargs.update(self.special_tokens_map)
        return YuanTokenizer.from_pretrained(self.tmpdirname, **kwargs)

    def get_rust_tokenizer(self, **kwargs):
        kwargs.update(self.special_tokens_map)
        return YuanTokenizerFast.from_pretrained(self.tmpdirname, **kwargs)

    def get_input_output_texts(self, tokenizer):
        # this case should cover
        # - NFC normalization (code point U+03D3 has different normalization forms under NFC, NFD, NFKC, and NFKD)
        # - the pretokenization rules (spliting digits and merging symbols with \n\r)
        input_text = "lower lower newer 010;}\n<|endoftext|>\u03d2\u0301"
        output_text = "lower lower newer 010;}\n<|endoftext|>\u03d3"
        return input_text, output_text

    def test_python_full_tokenizer(self):
        tokenizer = self.get_tokenizer()
        sequence, _ = self.get_input_output_texts(tokenizer)
        bpe_tokens = [
            "l",
            "o",
            "w",
            "er",
            "\u0120low",
            "er",
            "\u0120",
            "n",
            "e",
            "w",
            "er",
            "\u0120",
            "0",
            "1",
            "0",
            ";}\u010a",
            "<|endoftext|>",
            "\u00cf\u0135",
        ]
        tokens = tokenizer.tokenize(sequence)
        self.assertListEqual(tokens, bpe_tokens)

        input_tokens = tokens
        input_bpe_tokens = [75, 78, 86, 260, 259, 260, 220, 77, 68, 86, 260, 220, 15, 16, 15, 266, 270, 267]
        self.assertListEqual(tokenizer.convert_tokens_to_ids(input_tokens), input_bpe_tokens)

    @unittest.skip("We disable the test of pretokenization as it is not reversible.")
    def test_pretokenized_inputs(self):
        # the test case in parent class uses str.split to "pretokenize",
        # which eats the whitespaces, which, in turn, is not reversible.
        # the results, by nature, should be different.
        pass

    @unittest.skip("We disable the test of clean up tokenization spaces as it is not applicable.")
    def test_clean_up_tokenization_spaces(self):
        # it only tests bert-base-uncased and clean_up_tokenization_spaces is not applicable to this tokenizer
        pass

    def test_nfc_normalization(self):
        # per https://unicode.org/faq/normalization.html, there are three characters whose normalization forms
        # under NFC, NFD, NFKC, and NFKD are all different
        # using these, we can make sure only NFC is applied
        input_string = "\u03d2\u0301\u03d2\u0308\u017f\u0307"  # the NFD form
        output_string = "\u03d3\u03d4\u1e9b"  # the NFC form

        if self.test_slow_tokenizer:
            tokenizer = self.get_tokenizer()
            tokenizer_output_string, _ = tokenizer.prepare_for_tokenization(input_string)
            self.assertEqual(tokenizer_output_string, output_string)

        if self.test_rust_tokenizer:
            tokenizer = self.get_rust_tokenizer()
            # we can check the class of the normalizer, but it would be okay if Sequence([NFD, NFC]) is used
            # let's check the output instead
            tokenizer_output_string = tokenizer.backend_tokenizer.normalizer.normalize_str(input_string)
            self.assertEqual(tokenizer_output_string, output_string)

    def test_slow_tokenizer_token_with_number_sign(self):
        if not self.test_slow_tokenizer:
            return

        sequence = " ###"
        token_ids = [268, 269]

        tokenizer = self.get_tokenizer()
        self.assertListEqual(tokenizer.convert_tokens_to_ids(tokenizer.tokenize(sequence)), token_ids)

    def test_slow_tokenizer_decode_spaces_between_special_tokens_default(self):
        # YuanTokenizer changes the default `spaces_between_special_tokens` in `decode` to False
        if not self.test_slow_tokenizer:
            return

        # tokenizer has a special token: `"<|endfotext|>"` as eos, but it is not `legacy_added_tokens`
        # special tokens in `spaces_between_special_tokens` means spaces between `legacy_added_tokens`
        # that would be `"<|im_start|>"` and `"<|im_end|>"` in Yuan2M32 Models
        token_ids = [259, 260, 270, 271, 26]
        sequence = " lower<|endoftext|><|im_start|>;"
        sequence_with_space = " lower<|endoftext|> <|im_start|> ;"

        tokenizer = self.get_tokenizer()
        # let's add a legacy_added_tokens
        im_start = AddedToken(
            "<|im_start|>", single_word=False, lstrip=False, rstrip=False, special=True, normalized=False
        )
        tokenizer.add_tokens([im_start])

        # `spaces_between_special_tokens` defaults to False
        self.assertEqual(tokenizer.decode(token_ids), sequence)

        # but it can be set to True
        self.assertEqual(tokenizer.decode(token_ids, spaces_between_special_tokens=True), sequence_with_space)

    @slow
    def test_tokenizer_integration(self):
        sequences = [
            "Transformers (formerly known as pytorch-transformers and pytorch-pretrained-bert) provides "
            "general-purpose architectures (BERT, GPT-2, RoBERTa, XLM, DistilBert, XLNet...) for Natural "
            "Language Understanding (NLU) and Natural Language Generation (NLG) with over 32+ pretrained "
            "models in 100+ languages and deep interoperability between Jax, PyTorch and TensorFlow.",
            "馃 Transformers 鎻愪緵浜嗗彲浠ヨ交鏉惧湴涓嬭浇骞朵笖璁粌鍏堣繘鐨勯璁粌妯″瀷鐨?API 鍜屽伐鍏枫€備娇鐢ㄩ璁粌妯″瀷鍙互鍑忓皯璁＄畻娑堣€楀拰纰虫帓鏀撅紝骞朵笖鑺傜渷浠庡ご璁粌鎵€闇€瑕佺殑鏃堕棿鍜岃祫婧愩€?,
            """```python\ntokenizer = AutoTokenizer.from_pretrained("Yuan/yuan-tokenizer")\n"""
            """tokenizer("涓栫晫锛屼綘濂斤紒")```""",
        ]

        expected_encoding = {'input_ids': [[8963, 388, 320, 69514, 3881, 438, 4510, 27414, 32852, 388, 323, 4510, 27414, 21334, 35722, 1455, 529, 8, 5707, 4586, 58238, 77235, 320, 61437, 11, 479, 2828, 12, 17, 11, 11830, 61437, 64, 11, 1599, 10994, 11, 27604, 321, 33, 529, 11, 29881, 6954, 32574, 369, 18448, 11434, 45451, 320, 45, 23236, 8, 323, 18448, 11434, 23470, 320, 30042, 38, 8, 448, 916, 220, 18, 17, 10, 80669, 4119, 304, 220, 16, 15, 15, 10, 15459, 323, 5538, 94130, 2897, 1948, 619, 706, 11, 5355, 51, 21584, 323, 94986, 13], [144834, 80532, 93685, 83744, 34187, 73670, 104261, 29490, 62189, 103937, 104034, 102830, 98841, 104034, 104949, 9370, 5333, 58143, 102011, 1773, 37029, 98841, 104034, 104949, 73670, 101940, 100768, 104997, 33108, 100912, 105054, 90395, 100136, 106831, 45181, 64355, 104034, 113521, 101975, 33108, 85329, 1773, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643], [73594, 12669, 198, 85593, 284, 8979, 37434, 6387, 10442, 35722, 445, 48, 16948, 45274, 16948, 34841, 3135, 1138, 85593, 445, 99489, 3837, 108386, 6313, 899, 73594, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643, 151643]], 'attention_mask': [[1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1], [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]]}  # fmt: off

        self.tokenizer_integration_test_util(
            expected_encoding=expected_encoding,
            model_name="Yuan/yuan-tokenizer",
            revision="5909c8222473b2c73b0b73fb054552cd4ef6a8eb",
            sequences=sequences,
        )
