#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""Define evaluation method by Word Error Rate (CSJ corpus)."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import re
from tqdm import tqdm
import pandas as pd

from utils.io.labels.character import Idx2char
from utils.io.labels.word import Idx2word
from utils.evaluation.edit_distance import compute_wer
from utils.evaluation.resolving_unk import resolve_unk


def do_eval_wer(models, dataset, beam_width, max_decode_len,
                eval_batch_size=None, progressbar=False, resolving_unk=False):
    """Evaluate trained model by Word Error Rate.
    Args:
        models (list): the models to evaluate
        dataset: An instance of a `Dataset' class
        beam_width: (int): the size of beam
        max_decode_len (int): the length of output sequences
            to stop prediction when EOS token have not been emitted.
            This is used for seq2seq models.
        eval_batch_size (int, optional): the batch size when evaluating the model
        progressbar (bool, optional): if True, visualize the progressbar
        resolving_unk (bool, optional):
    Returns:
        wer (float): Word error rate
        df_wer (pd.DataFrame): dataframe of substitution, insertion, and deletion
    """
    # Reset data counter
    dataset.reset()

    idx2word = Idx2word(dataset.vocab_file_path)
    if resolving_unk:
        idx2char = Idx2char(dataset.vocab_file_path_sub)

    wer = 0
    sub, ins, dele, = 0, 0, 0
    num_words = 0
    if progressbar:
        pbar = tqdm(total=len(dataset))  # TODO: fix this
    while True:
        batch, is_new_epoch = dataset.next(batch_size=eval_batch_size)

        # Decode
        if len(models) > 1:
            assert models[0].model_type in ['ctc']
            for i, model in enumerate(models):
                probs, x_lens, perm_idx = model.posteriors(
                    batch['xs'], batch['x_lens'])
                if i == 0:
                    probs_ensenmble = probs
                else:
                    probs_ensenmble += probs
            probs_ensenmble /= len(models)

            best_hyps = models[0].decode_from_probs(
                probs_ensenmble, x_lens, beam_width=1)
        else:
            model = models[0]
            if model.model_type == 'nested_attention':
                if resolving_unk:
                    best_hyps, aw, best_hyps_sub, aw_sub, perm_idx = model.decode(
                        batch['xs'], batch['x_lens'],
                        beam_width=beam_width,
                        max_decode_len=max_decode_len,
                        max_decode_len_sub=100,
                        resolving_unk=True)
                else:
                    best_hyps, _, perm_idx = model.decode(
                        batch['xs'], batch['x_lens'],
                        beam_width=beam_width,
                        max_decode_len=max_decode_len,
                        max_decode_len_sub=100)
            else:
                if resolving_unk:
                    best_hyps, aw, perm_idx = model.decode(
                        batch['xs'], batch['x_lens'],
                        beam_width=beam_width,
                        max_decode_len=max_decode_len,
                        task_index=0, resolving_unk=True)
                    best_hyps_sub, aw_sub, _ = model.decode(
                        batch['xs'], batch['x_lens'],
                        beam_width=beam_width,
                        max_decode_len=100,
                        task_index=1, resolving_unk=True)
                else:
                    best_hyps, perm_idx = model.decode(
                        batch['xs'], batch['x_lens'],
                        beam_width=beam_width,
                        max_decode_len=max_decode_len)

        ys = batch['ys'][perm_idx]
        y_lens = batch['y_lens'][perm_idx]

        for b in range(len(batch['xs'])):

            ##############################
            # Reference
            ##############################
            if dataset.is_test:
                str_ref = ys[b][0]
                # NOTE: transcript is seperated by space('_')
            else:
                # Convert from list of index to string
                str_ref = idx2word(ys[b][:y_lens[b]])

            ##############################
            # Hypothesis
            ##############################
            str_hyp = idx2word(best_hyps[b])
            if 'attention' in model.model_type:
                str_hyp = str_hyp.split('>')[0]
                # NOTE: Trancate by the first <EOS>

                # Remove the last space
                if len(str_hyp) > 0 and str_hyp[-1] == '_':
                    str_hyp = str_hyp[:-1]

            # TODO: fix POS tag (nan -> 'nan')
            str_ref = str(str_ref)

            ##############################
            # Resolving UNK
            ##############################
            if resolving_unk and 'OOV' in str_hyp:
                str_hyp = resolve_unk(
                    str_hyp, best_hyps_sub[b], aw[b], aw_sub[b], idx2char)
                str_hyp = str_hyp.replace('*', '')

            ##############################
            # Post-proccessing
            ##############################
            # Remove noise labels
            str_ref = re.sub(r'[@>]+', '', str_ref)
            str_hyp = re.sub(r'[@>]+', '', str_hyp)
            # NOTE: @ means <sp>

            # Remove consecutive spaces
            str_ref = re.sub(r'[_]+', '_', str_ref)
            str_hyp = re.sub(r'[_]+', '_', str_hyp)

            # Compute WER
            try:
                wer_b, sub_b, ins_b, del_b = compute_wer(
                    ref=str_ref.split('_'),
                    hyp=str_hyp.split('_'),
                    normalize=False)
                wer += wer_b
                sub += sub_b
                ins += ins_b
                dele += del_b
                num_words += len(str_ref.split('_'))
            except:
                pass

            if progressbar:
                pbar.update(1)

        if is_new_epoch:
            break

    if progressbar:
        pbar.close()

    # Reset data counters
    dataset.reset()

    wer /= num_words
    sub /= num_words
    ins /= num_words
    dele /= num_words

    df_wer = pd.DataFrame(
        {'SUB': [sub * 100], 'INS': [ins * 100], 'DEL': [dele * 100]},
        columns=['SUB', 'INS', 'DEL'], index=['WER'])

    return wer, df_wer