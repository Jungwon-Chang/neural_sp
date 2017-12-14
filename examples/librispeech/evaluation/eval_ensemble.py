#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Evaluate the ensemble of trained models (Librispeech corpus)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from os.path import join, abspath, isfile
import sys
import yaml
import argparse
from glob import glob

sys.path.append(abspath('../../../'))
from models.pytorch.load_model import load
from examples.librispeech.data.load_dataset import Dataset
from examples.librispeech.metrics.cer_ensemble import do_eval_cer
from examples.librispeech.metrics.wer import do_eval_wer

parser = argparse.ArgumentParser()
parser.add_argument('--epoch', type=int, default=-1,
                    help='the epoch to restore')
parser.add_argument('--beam_width', type=int, default=1,
                    help='beam_width (int, optional): beam width for beam search.' +
                    ' 1 disables beam search, which mean greedy decoding.')
parser.add_argument('--eval_batch_size', type=int, default=1,
                    help='the size of mini-batch in evaluation')
parser.add_argument('--max_decode_length', type=int, default=600,  # or 100
                    help='the length of output sequences to stop prediction when EOS token have not been emitted')
parser.add_argument('--temperature', type=int, default=1,
                    help='Temperature parameter in the inference stage.')


def main():

    model_paths = [
        path for path in glob(join('/n/sd8/inaguma/result/pytorch/librispeech/ctc/character/100h', '*'))]

    if len(model_paths) == 0:
        raise ValueError('There are no model path.')

    args = parser.parse_args()

    models = []
    for model_path in model_paths:
        if isfile(join(model_path, 'complete.txt')):

            # Load config file
            with open(join(model_path, 'config.yml'), "r") as f:
                config = yaml.load(f)
                params = config['param']

            # Get voabulary number (excluding blank, <SOS>, <EOS> classes)
            with open('../metrics/vocab_num.yml', "r") as f:
                vocab_num = yaml.load(f)
                params['num_classes'] = vocab_num[params['data_size']
                                                  ][params['label_type']]

            # Load model
            model = load(model_type=params['model_type'], params=params)

            # GPU setting
            model.set_cuda(deterministic=False)

            # Restore the saved model
            checkpoint = model.load_checkpoint(
                save_path=model_path, epoch=-1)
            model.load_state_dict(checkpoint['state_dict'])

            # ***Change to evaluation mode***
            model.eval()

            models.append(model)

    print('=' * 30)
    print('  frame stack %d' % int(params['num_stack']))
    print('  beam width: %d' % args.beam_width)
    print('  ensemble: %d' % len(models))
    print('  temperature (training): %d' % params['logits_temperature'])
    print('  temperature (inference): %d' % args.temperature)
    print('=' * 30)

    # Load dataset
    vocab_file_path = '../metrics/vocab_files/' + \
        params['label_type'] + '_' + params['data_size'] + '.txt'
    test_clean_data = Dataset(
        model_type=params['model_type'],
        data_type='test_clean', data_size=params['data_size'],
        label_type=params['label_type'], vocab_file_path=vocab_file_path,
        batch_size=args.eval_batch_size, splice=params['splice'],
        num_stack=params['num_stack'], num_skip=params['num_skip'],
        sort_utt=False, save_format=params['save_format'])
    test_other_data = Dataset(
        model_type=params['model_type'],
        data_type='test_other', data_size=params['data_size'],
        label_type=params['label_type'], vocab_file_path=vocab_file_path,
        batch_size=args.eval_batch_size, splice=params['splice'],
        num_stack=params['num_stack'], num_skip=params['num_skip'],
        sort_utt=False, save_format=params['save_format'])

    print('=== Test Data Evaluation ===')
    if 'char' in params['label_type']:
        # test-clean
        cer_test_clean, wer_test_clean = do_eval_cer(
            models=models,
            model_type=params['model_type'],
            dataset=test_clean_data,
            label_type=params['label_type'],
            beam_width=args.beam_width,
            max_decode_length=args.max_decode_length,
            eval_batch_size=args.eval_batch_size,
            temperature=args.temperature,
            progressbar=True)
        print('  CER (clean): %f %%' % (cer_test_clean * 100))
        print('  WER (clean): %f %%' % (wer_test_clean * 100))

        # test-other
        cer_test_other, wer_test_other = do_eval_cer(
            models=models,
            model_type=params['model_type'],
            dataset=test_other_data,
            label_type=params['label_type'],
            beam_width=args.beam_width,
            max_decode_length=args.max_decode_length,
            eval_batch_size=args.eval_batch_size,
            progressbar=True)
        print('  CER (other): %f %%' % (cer_test_other * 100))
        print('  WER (other): %f %%' % (wer_test_other * 100))

    else:
        raise NotImplementedError
        # test-clean
        # wer_test_clean = do_eval_wer(
        #     model=model,
        #     model_type=params['model_type'],
        #     dataset=test_clean_data,
        #     label_type=params['label_type'],
        #     data_size=params['data_size'],
        #     beam_width=args.beam_width,
        #     max_decode_length=args.max_decode_length,
        #     eval_batch_size=args.eval_batch_size,
        #     progressbar=True)
        # print('  WER (clean): %f %%' % (wer_test_clean * 100))

        # test-other
        # wer_test_other = do_eval_wer(
        #     model=model,
        #     model_type=params['model_type'],
        #     dataset=test_other_data,
        #     label_type=params['label_type'],
        #     data_size=params['data_size'],
        #     beam_width=args.beam_width,
        #     max_decode_length=args.max_decode_length,
        #     eval_batch_size=args.eval_batch_size,
        #     progressbar=True)
        # print('  WER (other): %f %%' % (wer_test_other * 100))


if __name__ == '__main__':
    main()
