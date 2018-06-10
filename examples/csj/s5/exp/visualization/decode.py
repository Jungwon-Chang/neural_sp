#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Generate texts by the ASR model (CSJ corpus)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from os.path import join, abspath
import sys
import argparse
import re

sys.path.append(abspath('../../../'))
from models.load_model import load
from examples.csj.s5.exp.dataset.load_dataset import Dataset
from utils.config import load_config
from utils.evaluation.edit_distance import compute_wer

parser = argparse.ArgumentParser()
parser.add_argument('--data_save_path', type=str,
                    help='path to saved data')
parser.add_argument('--model_path', type=str,
                    help='path to the model to evaluate')
parser.add_argument('--epoch', type=int, default=-1,
                    help='the epoch to restore')
parser.add_argument('--eval_batch_size', type=int, default=1,
                    help='the size of mini-batch in evaluation')
parser.add_argument('--beam_width', type=int, default=1,
                    help='the size of beam')
parser.add_argument('--length_penalty', type=float, default=0,
                    help='length penalty in the beam search decoding')
parser.add_argument('--coverage_penalty', type=float, default=0,
                    help='coverage penalty in the beam search decoding')
parser.add_argument('--rnnlm_weight', type=float, default=0,
                    help='the weight of RNNLM score in the beam search decoding')
parser.add_argument('--rnnlm_path', default=None, type=str,  args='?',
                    help='path to the RMMLM')

MAX_DECODE_LEN_WORD = 100
MIN_DECODE_LEN_WORD = 1
MAX_DECODE_LEN_CHAR = 200
MIN_DECODE_LEN_CHAR = 1


def main():

    args = parser.parse_args()

    # Load a config file (.yml)
    params = load_config(join(args.model_path, 'config.yml'), is_eval=True)

    # Load dataset
    dataset = Dataset(
        data_save_path=args.data_save_path,
        input_freq=params['input_freq'],
        use_delta=params['use_delta'],
        use_double_delta=params['use_double_delta'],
        data_type='eval1',
        # data_type='eval2',
        # data_type='eval3',
        data_size=params['data_size'],
        label_type=params['label_type'],
        batch_size=args.eval_batch_size,
        sort_utt=False, reverse=False, tool=params['tool'])
    params['num_classes'] = dataset.num_classes
    params['num_classes_sub'] = dataset.num_classes

    # Load the ASR model
    model = load(model_type=params['model_type'],
                 params=params,
                 backend=params['backend'])

    # Restore the saved parameters
    model.load_checkpoint(save_path=args.model_path, epoch=args.epoch)

    if args.rnnlm_path is not None and args.rnnlm_weight > 0:
        # Load a config file (.yml)
        params_rnnlm = load_config(
            join(args.rnnlm_path, 'config.yml'), is_eval=True)

        assert params['label_type'] == params_rnnlm['label_type']
        params_rnnlm['num_classes'] = dataset.num_classes

        # Load RNLM
        rnnlm = load(model_type=params_rnnlm['model_type'],
                     params=params_rnnlm,
                     backend=params_rnnlm['backend'])

        # Restore the saved parameters
        rnnlm.load_checkpoint(save_path=args.rnnlm_path, epoch=-1)
        # NOTE: load the best model

        # NOTE: after load the rnn params are not a continuous chunk of memory
        # this makes them a continuous chunk, and will speed up forward pass
        rnnlm.rnn.flatten_parameters()
        # https://github.com/pytorch/examples/blob/master/word_language_model/main.py

        # Resister to the ASR model
        model.rnnlm_0 = rnnlm

    # GPU setting
    model.set_cuda(deterministic=False, benchmark=True)

    # sys.stdout = open(join(model.model_dir, 'decode.txt'), 'w')

    ######################################################################

    if dataset.label_type == 'word':
        map_fn = dataset.idx2word
        max_decode_len = MAX_DECODE_LEN_WORD
        min_decode_len = MIN_DECODE_LEN_WORD
    else:
        map_fn = dataset.idx2char
        max_decode_len = MAX_DECODE_LEN_CHAR
        min_decode_len = MIN_DECODE_LEN_CHAR

    for batch, is_new_epoch in dataset:
        # Decode
        if model.model_type == 'nested_attention':
            best_hyps, _, best_hyps_sub, _, perm_idx = model.decode(
                batch['xs'],
                beam_width=args.beam_width,
                max_decode_len=max_decode_len,
                max_decode_len_sub=max_decode_len,
                length_penalty=args.length_penalty,
                coverage_penalty=args.coverage_penalty,
                rnnlm_weight=args.rnnlm_weight)
        else:
            best_hyps, _, perm_idx = model.decode(
                batch['xs'],
                beam_width=args.beam_width,
                max_decode_len=max_decode_len,
                min_decode_len=min_decode_len,
                length_penalty=args.length_penalty,
                coverage_penalty=args.coverage_penalty,
                rnnlm_weight=args.rnnlm_weight)

        ys = [batch['ys'][i] for i in perm_idx]

        for b in range(len(batch['xs'])):
            # Reference
            if dataset.is_test:
                str_ref = ys[b]
                # NOTE: transcript is seperated by space('_')
            else:
                str_ref = map_fn(ys[b])

            # Hypothesis
            str_hyp = map_fn(best_hyps[b])

            print('----- wav: %s -----' % batch['input_names'][b])
            print('Ref: %s' % str_ref.replace('_', ' '))
            print('Hyp: %s' % str_hyp.replace('_', ' '))

            # Remove noisy labels
            str_hyp = str_hyp.replace('>', '')

            # Remove consecutive spaces
            str_hyp = re.sub(r'[_]+', '_', str_hyp)
            if str_hyp[-1] == '_':
                str_hyp = str_hyp[:-1]

            try:
                if dataset.label_type in ['word', 'character_wb']:
                    wer, _, _, _ = compute_wer(ref=str_ref.split('_'),
                                               hyp=str_hyp.split('_'),
                                               normalize=True)
                    print('WER: %.3f %%' % (wer * 100))
                else:
                    cer, _, _, _ = compute_wer(
                        ref=list(str_ref.replace('_', '')),
                        hyp=list(str_hyp.replace('_', '')),
                        normalize=True)
                    print('CER: %.3f %%' % (cer * 100))
            except:
                print('--- skipped ---')

        if is_new_epoch:
            break


if __name__ == '__main__':
    main()
