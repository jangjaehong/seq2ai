# 어휘 사전과 워드 임베딩을 만들고, 학습을 위해 대화 데이터를 읽어들이는 유틸리티들의 모음
import tensorflow as tf
import numpy as np
import re
import db
from config import FLAGS

class Dialog():

    _PAD_ = "<PAD>"  # 빈칸 채우는 심볼
    _STA_ = "<S>"  # 디코드 입력 시퀀스의 시작 심볼
    _EOS_ = "<E>"  # 디코드 입출력 시퀀스의 종료 심볼
    _UNK_ = "<UNK>"  # 사전에 없는 단어를 나타내는 심볼

    _PAD_ID_ = 0
    _STA_ID_ = 1
    _EOS_ID_ = 2
    _UNK_ID_ = 3
    _PRE_DEFINED_ = [_PAD_, _STA_, _EOS_, _UNK_]

    def __init__(self):
        self.vocab_list = []
        self.vocab_dict = {}
        self.vocab_size = 0
        self.examples = []
        self.input_size = 0

        self._index_in_epoch = 0

    def decode(self, indices, string=False):
        print("indices:", indices)
        tokens = [[self.vocab_list[i] for i in dec] for dec in indices]

        if string:
            return self._decode_to_string(tokens[0])
        else:
            return tokens

    def _decode_to_string(self, tokens):
        text = ' '.join(tokens)
        return text.strip()

    def cut_eos(self, indices):
        eos_idx = indices.index(self._EOS_ID_)
        return indices[:eos_idx]

    def is_eos(self, voc_id):
        return voc_id == self._EOS_ID_

    def is_defined(self, voc_id):
        return voc_id in self._PRE_DEFINED_

    def _max_len2(self, batch_set):
        max_size = 0
        for sentence in batch_set:
            if len(sentence) > max_size:
                max_size = len(sentence)
        if self.vocab_size > max_size:
            self.input_size = self.vocab_size
        else:
            self.input_size = max_size


    def _max_len(self, batch_set):
        max_len_input = 0
        max_len_output = 0

        for i in range(0, len(batch_set), 2):
            len_input = len(batch_set[i])
            len_output = len(batch_set[i+1])
            if len_input > max_len_input:
                max_len_input = len_input
            if len_output > max_len_output:
                max_len_output = len_output

        return max_len_input, max_len_output + 1

    def _pad(self, seq, max_len, start=None, eos=None):
        if start:
            padded_seq = [self._STA_ID_] + seq
        elif eos:
            padded_seq = seq + [self._EOS_ID_]
        else:
            padded_seq = seq

        if len(padded_seq) < max_len:
            return padded_seq + ([self._PAD_ID_] * (max_len - len(padded_seq)))
        else:
            return padded_seq

    def _pad_left(self, seq, max_len):
        if len(seq) < max_len:
            return ([self._PAD_ID_] * (max_len - len(seq))) + seq
        else:
            return seq

    def transform(self, input, output, input_max, output_max):
        enc_input = self._pad(input, input_max)
        dec_input = self._pad(output, output_max, start=True)
        target = self._pad(output, output_max, eos=True)

        # 구글 방식으로 입력을 인코더에 역순으로 입력한다.
        enc_input.reverse()

        enc_input = np.eye(self.vocab_size)[enc_input]
        dec_input = np.eye(self.vocab_size)[dec_input]

        return enc_input, dec_input, target

    def next_batch(self, batch_size):
        enc_input = []
        dec_input = []
        target = []

        start = self._index_in_epoch

        if self._index_in_epoch + batch_size < len(self.examples) - 1:
            self._index_in_epoch = self._index_in_epoch + batch_size
        else:
            self._index_in_epoch = 0

        batch_set = self.examples[start:start+batch_size]

        # 작은 데이터셋을 실험하기 위한 꼼수
        # 현재의 답변을 다음 질문의 질문으로 하고, 다음 질문을 답변으로 하여 데이터를 늘린다.
        if FLAGS.data_loop is True:
           batch_set = batch_set + batch_set[1:] + batch_set[0:1]

        # TODO: 구글처럼 버킷을 이용한 방식으로 변경
        # 간단하게 만들기 위해 구글처럼 버킷을 쓰지 않고 같은 배치는 같은 사이즈를 사용하도록 만듬
        max_len_input, max_len_output = self._max_len(batch_set)

        for i in range(0, len(batch_set) - 1, 2):
            enc, dec, tar = self.transform(batch_set[i], batch_set[i+1],
                                           max_len_input, max_len_output)

            enc_input.append(enc)
            dec_input.append(dec)
            target.append(tar)

        return enc_input, dec_input, target

    def tokens_to_ids(self, tokens):
        ids = []

        for t in tokens:
            if t in self.vocab_dict:
                ids.append(self.vocab_dict[t])
            else:
                ids.append(self._UNK_ID_)

        return ids

    def ids_to_tokens(self, ids):
        tokens = []

        for i in ids:
            tokens.append(self.vocab_list[i])

        return tokens

    def tokenizer(self, sentence_list, build=None, load=None):
        words = []
        #_TOKEN_RE_ = re.compile("([.,!?\"':;)(])")
        for sentence in sentence_list:
            for fragment in sentence:
                words.extend([fragment.strip().split()])
        if build:
            build_words = []
            for word_list in words:
                for word in word_list:
                    build_words.append(word)
            return build_words
        if load:
            return words
    # 어휘 사전 제작 및 디비에 저장
    def build_vocab(self):
        sequence_data = db.select_chat_sequence()
        words = self.tokenizer(sequence_data, build=True)

        # 어휘를 디비에 저장
        words_dic = [{'vocab': r, 'morpheme': ''} for r in list(set(words))]
        db.delete_in_chat_vocab(words_dic)

    # 어휘 사전 로드
    def load_vocab(self):
        self.vocab_list = self._PRE_DEFINED_ + []

        vocab_list = db.select_chat_vocab()
        for row in vocab_list:
            self.vocab_list.append(row[1])

        # {'_PAD_': 0, '_STA_': 1, '_EOS_': 2, '_UNK_': 3, 'Hello': 4, 'World': 5, ...}
        self.vocab_dict = {n: i for i, n in enumerate(self.vocab_list)}
        self.vocab_size = len(self.vocab_list)
        print('어휘 사전을 불러왔습니다.')


    # 예제 로드
    def load_examples(self):
        self.examples = []
        sequence_data = db.select_chat_sequence()
        self._max_len2(sequence_data)
        tokens = self.tokenizer(sequence_data, load=True)
        for sentence in tokens:
            ids = self.tokens_to_ids(sentence)
            self.examples.append(ids)

def main(_):
    dialog = Dialog()

    if FLAGS.voc_test:
        print("데이터베이스 데이터를 통해 어휘 사전을 테스트합니다.")
        dialog.load_vocab()
        dialog.load_examples()

        enc, dec, target = dialog.next_batch(10)
      #  print(target)
        enc, dec, target = dialog.next_batch(10)
       # print(target)

    elif FLAGS.voc_build:
        dialog.build_vocab()

    elif FLAGS.voc_test:
        dialog.load_vocab()
        print(dialog.vocab_dict)


if __name__ == "__main__":
    tf.app.run()