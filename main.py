# Copyright 2015 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#==============================================================================

"""Based on the TensorFlow tutorial for building a PTB LSTM model."""
from __future__ import division

import time

import numpy as np
import tensorflow as tf

from config import Config
import reader

flags = tf.flags
logging = tf.logging

FLAGS = flags.FLAGS


class LMModel(object):
    """The language model."""

    def __init__(self, is_training, config, vocab):
        self.batch_size = batch_size = config.batch_size
        self.num_steps = num_steps = config.num_steps
        size = config.hidden_size
        vocab_size = config.vocab_size

        self.input_data = tf.placeholder(tf.int32, [batch_size, num_steps])
        self.targets = tf.placeholder(tf.int32, [batch_size, num_steps])
        self.mask = tf.placeholder(tf.float32, [batch_size, num_steps])
        if config.conditional:
            self.aux_data = {}
            for feat, dims in config.mimic_embeddings.items():
                if dims > 0:
                    self.aux_data[feat] = tf.placeholder(tf.int32, [batch_size, None])

        lstm_cell = tf.nn.rnn_cell.BasicLSTMCell(size)
        if is_training and config.keep_prob < 1:
            lstm_cell = tf.nn.rnn_cell.DropoutWrapper(lstm_cell, output_keep_prob=config.keep_prob)
        cell = tf.nn.rnn_cell.MultiRNNCell([lstm_cell] * config.num_layers)

        self.initial_state = cell.zero_state(batch_size, tf.float32)

        with tf.device("/cpu:0"):
            embedding = tf.get_variable("embedding", [vocab_size, config.learn_wordemb_size])
            if config.pretrained_emb:
                cembedding = tf.constant(vocab.embeddings, dtype=embedding.dtype,
                                         name="pre_embedding")
                embedding = tf.concat(1, [embedding, cembedding])
            inputs = tf.nn.embedding_lookup(embedding, self.input_data)

        if config.conditional:
            emb_size = max(config.mimic_embeddings.values())
            emb_list = []
            for i, (feat, dims) in enumerate(config.mimic_embeddings.items()):
                try:
                    vocab_aux = len(vocab.aux_list[feat])
                except KeyError:
                    vocab_aux = 2 # binary
                with tf.device("/cpu:0"):
                    embedding = tf.get_variable("embedding_"+feat, [vocab_aux, config.mimic_embeddings[feat]])
                    val_embedding = tf.nn.embedding_lookup(embedding, self.aux_data[feat])
                    val_embedding = tf.reshape(val_embedding, [-1, config.mimic_embeddings[feat]])
                transform_w = tf.get_variable("emb_transform_"+feat, [config.mimic_embeddings[feat], emb_size])
                transformed = tf.matmul(val_embedding, transform_w)
                reshaped = tf.reshape(transformed, tf.pack([batch_size, -1, emb_size]))
                reduced = tf.reduce_sum(reshaped, 1)
                emb_list.append(reduced)

            structured_inputs = sum(emb_list)
            inputs += tf.reduce_sum(structured_inputs) # TODO remove this, and decouple structured dims

        if is_training and config.keep_prob < 1:
            inputs = tf.nn.dropout(inputs, config.keep_prob)

        inputs = [tf.squeeze(input_, [1]) for input_ in tf.split(1, num_steps, inputs)]
        outputs, state = tf.nn.rnn(cell, inputs, initial_state=self.initial_state)

        output = tf.reshape(tf.concat(1, outputs), [-1, size])
        softmax_w = tf.get_variable("softmax_w", [size, vocab_size])
        softmax_b = tf.get_variable("softmax_b", [vocab_size])
        logits = tf.matmul(output, softmax_w) + softmax_b
        loss = tf.nn.seq2seq.sequence_loss_by_example(
                [logits],
                [tf.reshape(self.targets, [-1])],
                [tf.reshape(self.mask, [-1])])
        self.cost = cost = tf.reduce_sum(loss) / batch_size
        self.final_state = state

        if not is_training:
            return

        self.lr = tf.Variable(0.0, trainable=False)
        tvars = tf.trainable_variables()
        grads, _ = tf.clip_by_global_norm(tf.gradients(cost, tvars),
                                          config.max_grad_norm)
        optimizer = tf.train.AdamOptimizer(self.lr)
        self.train_op = optimizer.apply_gradients(zip(grads, tvars))

    def assign_lr(self, session, lr_value):
        session.run(tf.assign(self.lr, lr_value))


def run_epoch(session, m, eval_op, config, vocab, verbose=False):
    """Runs the model on the given data."""
    start_time = time.time()
    costs = 0.0
    iters = 0
    zero_state = m.initial_state.eval()
    for step, (x, y, mask, aux, new_batch) in enumerate(reader.mimic_iterator(config, vocab)):
        f_dict = {m.input_data: x,
                  m.targets: y,
                  m.mask: mask}
        if new_batch:
            f_dict[m.initial_state] = zero_state
        else:
            f_dict[m.initial_state] = state
        if config.conditional:
            for feat, vals in aux.items():
                f_dict[m.aux_data[feat]] = vals
        cost, state, _ = session.run([m.cost, m.final_state, eval_op], f_dict)
        costs += cost
        iters += m.num_steps

        if verbose and step % config.print_every == 0:
            print("%d  perplexity: %.3f speed: %.0f wps" %
                        (step, np.exp(costs / iters),
                         iters * m.batch_size / (time.time() - start_time)))

    return np.exp(costs / iters)


def main(_):
    config = Config()
    if config.conditional:
        print 'Training a conditional language model for MIMIC'
    else:
        print 'Training an unconditional language model for MIMIC'
    vocab = reader.Vocab(config)

    config_proto = tf.ConfigProto()
    config_proto.gpu_options.allow_growth = True
    with tf.Graph().as_default(), tf.Session(config=config_proto) as session:
        initializer = tf.random_uniform_initializer(-config.init_scale,
                                                    config.init_scale)
        with tf.variable_scope("model", reuse=None, initializer=initializer):
            m = LMModel(is_training=True, config=config, vocab=vocab)
        tf.initialize_all_variables().run()

        for i in range(config.max_epoch):
            #lr_decay = config.lr_decay ** max(i - config.max_epoch, 0.0)
            m.assign_lr(session, config.learning_rate) #* lr_decay)

            print("Epoch: %d Learning rate: %.3f" % (i + 1, session.run(m.lr)))
            train_perplexity = run_epoch(session, m, m.train_op, config, vocab,
                                         verbose=True)
            print("Epoch: %d Train Perplexity: %.3f" % (i + 1,
                                                        train_perplexity))


if __name__ == "__main__":
    tf.app.run()
