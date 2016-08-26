import collections

import tensorflow as tf

flags = tf.flags

# command-line config
flags.DEFINE_string ("data_path",           "data",              "Data path")
flags.DEFINE_string ("save_file",           "models/recent.dat", "Save file prefix")
flags.DEFINE_string ("timeline_file",       "timeline.json",     "File to save profiling " \
                                                                 "information to")
flags.DEFINE_string ("load_file",           "",                  "File to load model from")
flags.DEFINE_string ("load_struct_file",    "",                  "File to load structured " \
                                                                 "embeddings from")
flags.DEFINE_string ("load_emb_file",       "",                  "File to load word embeddings " \
                                                                 "from")
flags.DEFINE_string ("dump_results_file",   "",                  "File to dump predictions into")
flags.DEFINE_string ("load_cond_results",   "",                  "File to load conditional " \
                                                                 "predictions from")
flags.DEFINE_string ("load_uncond_results", "",                  "File to load unconditional " \
                                                                 "predictions from")

flags.DEFINE_float  ("learning_rate",    1e-3,    "Optimizer initial learning rate")
flags.DEFINE_float  ("learning_rate2",   1e-4,    "Optimizer decayed learning rate")
flags.DEFINE_integer("decay_step",       1000000, "Step to decay learning rate at")
flags.DEFINE_integer("decay_epoch",      3,       "Epoch to decay learning rate at")
flags.DEFINE_float  ("max_grad_norm",    5.0,     "Gradient clipping for RNNs")
flags.DEFINE_integer("num_layers",       2,       "Number of LSTM layers")
flags.DEFINE_integer("num_steps",        32,      "Number of steps to unroll for RNNs")
flags.DEFINE_integer("context_size",     6,       "Context size for CBOW")
flags.DEFINE_integer("hidden_size",      192,     "Hidden state size")
flags.DEFINE_bool   ("distance_dep",     True,    "Distance-dependent word embeddings")
flags.DEFINE_integer("word_emb_size",    256,     "Number of learnable dimensions in word " \
                                                  "embeddings")
flags.DEFINE_float  ("struct_l1_weight", 0.0,     "Weight for minimizing L1-norm of structured " \
                                                  "embeddings")
flags.DEFINE_float  ("struct_l2_weight", 0.0,     "Weight for minimizing L2-norm of structured " \
                                                  "embeddings")
flags.DEFINE_integer("max_steps",        9999999, "Maximum number of steps to run for")
flags.DEFINE_integer("max_epoch",        6,       "Maximum number of epochs to run for")
flags.DEFINE_integer("softmax_samples",  1000,    "Number of classes to sample for softmax")
flags.DEFINE_float  ("keep_prob",        1.0,     "Dropout keep probability")
flags.DEFINE_float  ("struct_keep_prob", 1.0,     "Structural info dropout keep probability")
flags.DEFINE_bool   ("mean_varlen_embs", False,   "Mean variable-len struct embeddings instead " \
                                                  "of sum")
flags.DEFINE_integer("batch_size",       32,      "Batch size")
flags.DEFINE_integer("print_every",      500,     "Print every these many steps")
flags.DEFINE_integer("save_every",       10000,   "Save every these many steps")
flags.DEFINE_bool   ("save_overwrite",   True,    "Overwrite the same file each time")
flags.DEFINE_bool   ("pretrained_emb",   False,   "Use pretrained embeddings")
flags.DEFINE_bool   ("conditional",      True,    "Use a conditional language model")
flags.DEFINE_bool   ("training",         True,    "Training mode, turn off for testing")
flags.DEFINE_string ("optimizer",        'adam',  "Optimizer to use (sgd, adam, adagrad, " \
                                                  "adadelta)")
flags.DEFINE_bool   ("force_trainset",   False,   "Force training set even for testing")
flags.DEFINE_string ("inspect",          'none',  "Inspect the loaded/new model (none, embs, " \
                                                  "struct, compare, transforms)")
flags.DEFINE_bool   ("profile",          False,   "Do profiling on first batch")
flags.DEFINE_bool   ("recurrent",        False,   "Use a recurrent language model")
flags.DEFINE_bool   ("struct_only",      False,   "Use a model with only structured data")
flags.DEFINE_bool   ("use_hsm",          False,   "Use two-level hierarchical softmax")
flags.DEFINE_integer("data_rand_buffer", 25000,   "Number of buffered CBOW minibatches to " \
                                                  "randomize")
flags.DEFINE_integer("samples_per_note", 20,      "Number of CBOW minibatches per note")

# making the sum of the struct embeddings sum to a multiple of 32 (they're concatenated)
flags.DEFINE_integer("dims_gender",         1,   "Dimensionality for gender")
flags.DEFINE_integer("dims_has_dod",        1,   "Dimensionality for has_dod")
flags.DEFINE_integer("dims_has_icu_stay",   1,   "Dimensionality for has_icu_stay")
flags.DEFINE_integer("dims_admission_type", 4,   "Dimensionality for admission_type")
flags.DEFINE_integer("dims_diagnoses",      127, "Dimensionality for diagnoses")
flags.DEFINE_integer("dims_procedures",     126, "Dimensionality for procedures")
flags.DEFINE_integer("dims_labs",           126, "Dimensionality for labs")
flags.DEFINE_integer("dims_prescriptions",  126, "Dimensionality for prescriptions")


class Config(object):
    mimic_embeddings = collections.OrderedDict({})

    # additional config
    fixed_len_features = set(['gender', 'has_dod', 'has_icu_stay', 'admission_type'])
    var_len_features = set(['diagnoses', 'procedures', 'labs', 'prescriptions'])
    testing_splits = range(1)
    training_splits = range(1,100)


    def __init__(self):
        for k, v in sorted(flags.FLAGS.__dict__['__flags'].items(), key=lambda x: x[0]):
            setattr(self, k, v)
            if k.startswith('dims_'):
                self.mimic_embeddings[k[len('dims_'):]] = v

        if not self.recurrent:
            self.num_steps = self.context_size # reuse the num_steps config for FF
            assert self.num_steps % 2 == 0
