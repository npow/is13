import theano
import numpy
import os

from theano import tensor as T
from theano.printing import Print as pp
from collections import OrderedDict

def batch_norm(x):
    return T.sqrt(T.sum(T.sqr(x), axis=1))

def batch_cdist(matrix, vector):
    matrix = matrix.T
    dotted = T.dot(vector, matrix.T)

    matrix_norms = batch_norm(matrix)
    vector_norms = batch_norm(vector)

    matrix_vector_norms = T.outer(vector_norms, matrix_norms)
    neighbors = dotted / matrix_vector_norms
    return 1. - neighbors

def norm(x):
    axis = None if x.ndim == 1 else 1
    return T.sqrt(T.sum(T.sqr(x), axis=axis))

def cdist(matrix, vector):
    matrix = matrix.T
    dotted = T.dot(matrix, vector)
    matrix_norms = norm(matrix)
    vector_norms = norm(vector)
    matrix_vector_norms = matrix_norms * vector_norms
    neighbors = dotted / matrix_vector_norms
    return 1. - neighbors

class model(object):
    
    def __init__(self, nh, nc, ne, de, cs, memory_size=100, n_memory_slots=1):
        '''
        nh :: dimension of the hidden layer
        nc :: number of classes
        ne :: number of word embeddings in the vocabulary
        de :: dimension of the word embeddings
        cs :: word window context size 
        '''
        # parameters of the model
        self.emb = theano.shared(0.2 * numpy.random.uniform(-1.0, 1.0,\
                   (ne+1, de)).astype(theano.config.floatX)) # add one for PADDING at the end
        self.Wx  = theano.shared(0.2 * numpy.random.uniform(-1.0, 1.0,\
                   (nh, de*cs)).astype(theano.config.floatX))
        self.Wh  = theano.shared(0.2 * numpy.random.uniform(-1.0, 1.0,\
                   (nh, memory_size)).astype(theano.config.floatX))
        self.W   = theano.shared(0.2 * numpy.random.uniform(-1.0, 1.0,\
                   (nc, nh)).astype(theano.config.floatX))
        self.bh  = theano.shared(numpy.zeros(nh, dtype=theano.config.floatX))
        self.b   = theano.shared(numpy.zeros(nc, dtype=theano.config.floatX))
        self.h0  = theano.shared(0.2 * numpy.random.uniform(-1.0, 1.0, (nh,)).astype(theano.config.floatX))

        print 'de*cs: ', de*cs

        self.M = theano.shared(0.2 * numpy.random.uniform(-1.0, 1.0, (memory_size, n_memory_slots)).astype(theano.config.floatX))
        self.Wk  = theano.shared(0.2 * numpy.random.uniform(-1.0, 1.0, (memory_size, nh)).astype(theano.config.floatX))
        self.Wg  = theano.shared(0.2 * numpy.random.uniform(-1.0, 1.0, (de*cs, 1)).astype(theano.config.floatX))
        self.Wb  = theano.shared(0.2 * numpy.random.uniform(-1.0, 1.0, (nh, 1)).astype(theano.config.floatX))
        self.Wv  = theano.shared(0.2 * numpy.random.uniform(-1.0, 1.0, (memory_size, nh)).astype(theano.config.floatX))
        self.We  = theano.shared(0.2 * numpy.random.uniform(-1.0, 1.0, (n_memory_slots, nh)).astype(theano.config.floatX))
        self.w0  = theano.shared(0.2 * numpy.random.uniform(-1.0, 1.0, (n_memory_slots,)).astype(theano.config.floatX))

        self.bk  = theano.shared(numpy.zeros(memory_size, dtype=theano.config.floatX))
        self.bg  = theano.shared(numpy.zeros(1, dtype=theano.config.floatX))
        self.bb  = theano.shared(numpy.zeros(nh, dtype=theano.config.floatX))
        self.bv  = theano.shared(numpy.zeros(memory_size, dtype=theano.config.floatX))
        self.be  = theano.shared(numpy.zeros(n_memory_slots, dtype=theano.config.floatX))

        # bundle
        self.params = [ self.emb, self.Wx, self.Wh, self.W, self.bh, self.b, self.h0, self.Wg, self.Wb, self.Wv, self.We, self.Wk ]
        self.names  = [ 'embeddings', 'Wx', 'Wh', 'W', 'bh', 'b', 'h0', 'Wg', 'Wb', 'Wv', 'We', 'Wk']
        idxs = T.imatrix() # as many columns as context window size/lines as words in the sentence
#        idxs = pp(message='idxs', attrs=['shape'])(idxs)
        x = self.emb[idxs].reshape((idxs.shape[0], de*cs))
#        x = pp(message='x', attrs=['shape'])(x)
        y    = T.iscalar('y') # label

        def recurrence(x_t, h_tm1, w_previous, M_previous):
#            x_t = pp(message='x_t', attrs=['shape'])(x_t)
            zzz = T.dot(x_t, self.Wg)
#            zzz = pp(message='zzz', attrs=['shape'])(zzz)
            g_t = T.nnet.sigmoid(zzz)# + self.bg)
#            g_t = pp(message='g_t', attrs=['shape'])(g_t)

            ### EXTERNAL MEMORY READ
            # eqn 11
            k = T.dot(self.Wk, h_tm1)# + self.bk
#            k = pp(message='k', attrs=['shape'])(k)

            # eqn 13
            beta_pre = T.dot(h_tm1, self.Wb)# + self.bb
            beta = T.log(1 + T.exp(beta_pre))
#            beta = pp(message='beta', attrs=['shape'])(beta)

            # eqn 12
            w_hat = cdist(M_previous, k)
            w_hat = T.exp(beta * w_hat)
            w_hat /= T.sum(w_hat)#, axis=1).dimshuffle(0, 'x')
#            w_hat = pp(message='w_hat', attrs=['shape'])(w_hat)

            # eqn 14
            w_t = (1 - g_t)*w_previous + g_t*w_hat
#            w_t = pp(message='w_t', attrs=['shape'])(w_t)

            # eqn 15
            c = T.dot(M_previous, w_t)
#            c = pp(message='c', attrs=['shape'])(c)

            ### EXTERNAL MEMORY UPDATE
            # eqn 16
            v = T.dot(self.Wv, h_tm1)# + self.bv
#            v = pp(message='v', attrs=['shape'])(v)

            # eqn 17
            e = T.nnet.sigmoid(T.dot(self.We, h_tm1))# + self.be)
#            e = pp(message='e', attrs=['shape'])(e)
            f = 1. - w_t * e
#            f = pp(message='f', attrs=['shape'])(f)

            # eqn 18
            f_diag = T.diag(f)
            M_t = T.dot(M_previous, f_diag) + T.dot(v.reshape((-1,1)), w_t.reshape((1,-1)))
#            M_t = pp(message='M_t', attrs=['shape'])(M_t)

            A = T.dot(self.Wx, x_t)
#            A = pp(message='A', attrs=['shape'])(A)
            B = T.dot(self.Wh, c)
#            B = pp(message='B', attrs=['shape'])(B)

            h_t = T.nnet.sigmoid(A + B + self.bh)
            s_t = T.nnet.softmax(T.dot(self.W, h_t) + self.b)

            return [h_t, s_t, w_t, M_t]

        [h, s, _, M], _ = theano.scan(fn=recurrence, \
            sequences=x, outputs_info=[self.h0, None, self.w0, self.M], \
            n_steps=x.shape[0])

        self.M = M

        p_y_given_x_lastword = s[-1,0,:]
        p_y_given_x_sentence = s[:,0,:]
        y_pred = T.argmax(p_y_given_x_sentence, axis=1)

        # cost and gradients and learning rate
        lr = T.scalar('lr')
        nll = -T.mean(T.log(p_y_given_x_lastword)[y])
        gradients = T.grad( nll, self.params )
        updates = OrderedDict(( p, p-lr*g ) for p, g in zip( self.params , gradients))
        
        # theano functions
        self.classify = theano.function(inputs=[idxs], outputs=y_pred)

        self.train = theano.function( inputs  = [idxs, y, lr],
                                      outputs = nll,
                                      updates = updates )

        self.normalize = theano.function( inputs = [],
                         updates = {self.emb:\
                         self.emb/T.sqrt((self.emb**2).sum(axis=1)).dimshuffle(0,'x')})

    def save(self, folder):   
        for param, name in zip(self.params, self.names):
            numpy.save(os.path.join(folder, name + '.npy'), param.get_value())
