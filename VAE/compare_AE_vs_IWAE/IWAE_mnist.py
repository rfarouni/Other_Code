





import numpy as np
import tensorflow as tf
import random
import math
from os.path import expanduser
home = expanduser("~")
import time
# import imageio


######################################################################
#OTHER
######################################################################

def xavier_init(fan_in, fan_out, constant=1): 
    """ Xavier initialization of network weights"""
    # https://stackoverflow.com/questions/33640581/how-to-do-xavier-initialization-on-tensorflow
    low = -constant*np.sqrt(6.0/(fan_in + fan_out)) 
    high = constant*np.sqrt(6.0/(fan_in + fan_out))
    return tf.random_uniform((fan_in, fan_out), 
                             minval=low, maxval=high, 
                             dtype=tf.float32)

######################################################################
#MODEL
######################################################################

class IWAE():

    def __init__(self, network_architecture, transfer_fct=tf.nn.softplus, learning_rate=0.001, batch_size=5, n_particles=3):
        self.network_architecture = network_architecture
        self.transfer_fct = transfer_fct
        self.learning_rate = learning_rate
        self.batch_size = batch_size
        self.n_particles = n_particles
        
        # tf Graph input
        self.x = tf.placeholder(tf.float32, [None, network_architecture["n_input"]])
        
        # Create autoencoder network
        # self._create_network()
        self.network_weights = self._initialize_weights(**self.network_architecture)

        # Define loss function based variational upper-bound and corresponding optimizer
        self._create_loss_optimizer()
        
        # Initializing the tensor flow variables
        init = tf.initialize_all_variables()


        # self.check_nan = tf.add_check_numerics_ops()
        # self.weight_sum = 

        # Launch the session
        self.sess = tf.InteractiveSession()
        self.sess.run(init)


    def _initialize_weights(self, n_hidden_recog_1, n_hidden_recog_2, 
                            n_hidden_gener_1,  n_hidden_gener_2, 
                            n_input, n_z):
        all_weights = dict()
        all_weights['weights_recog'] = {
            'h1': tf.Variable(xavier_init(n_input, n_hidden_recog_1)),
            'h2': tf.Variable(xavier_init(n_hidden_recog_1, n_hidden_recog_2)),
            'out_mean': tf.Variable(xavier_init(n_hidden_recog_2, n_z)),
            'out_log_sigma': tf.Variable(xavier_init(n_hidden_recog_2, n_z))}
        all_weights['biases_recog'] = {
            'b1': tf.Variable(tf.zeros([n_hidden_recog_1], dtype=tf.float32)),
            'b2': tf.Variable(tf.zeros([n_hidden_recog_2], dtype=tf.float32)),
            'out_mean': tf.Variable(tf.zeros([n_z], dtype=tf.float32)),
            'out_log_sigma': tf.Variable(tf.zeros([n_z], dtype=tf.float32))}
        all_weights['weights_gener'] = {
            'h1': tf.Variable(xavier_init(n_z, n_hidden_gener_1)),
            'h2': tf.Variable(xavier_init(n_hidden_gener_1, n_hidden_gener_2)),
            'out_mean': tf.Variable(xavier_init(n_hidden_gener_2, n_input)),
            'out_log_sigma': tf.Variable(xavier_init(n_hidden_gener_2, n_input))}
        all_weights['biases_gener'] = {
            'b1': tf.Variable(tf.zeros([n_hidden_gener_1], dtype=tf.float32)),
            'b2': tf.Variable(tf.zeros([n_hidden_gener_2], dtype=tf.float32)),
            'out_mean': tf.Variable(tf.zeros([n_input], dtype=tf.float32)),
            'out_log_sigma': tf.Variable(tf.zeros([n_input], dtype=tf.float32))}
        return all_weights
            


    def _recognition_network(self, x_t, weights, biases):
        # Generate probabilistic encoder (recognition network), which
        # maps inputs onto a normal distribution in latent space.

        layer_1 = self.transfer_fct(tf.add(tf.matmul(x_t, weights['h1']), biases['b1'])) 
        layer_2 = self.transfer_fct(tf.add(tf.matmul(layer_1, weights['h2']), biases['b2'])) 

        z_mean_t = tf.add(tf.matmul(layer_2, weights['out_mean']),biases['out_mean'])
        z_log_sigma_sq_t = \
            tf.add(tf.matmul(layer_2, weights['out_log_sigma']), 
                   biases['out_log_sigma'])

        return (z_mean_t, z_log_sigma_sq_t)

    def _generator_network(self, z, weights, biases):
        # Generate probabilistic decoder (decoder network), which
        # maps points in latent space onto a Bernoulli distribution in data space.
        # Used for reconstruction

        layer_1 = self.transfer_fct(tf.add(tf.matmul(z, weights['h1']), 
                                           biases['b1'])) 
        layer_2 = self.transfer_fct(tf.add(tf.matmul(layer_1, weights['h2']), 
                                           biases['b2'])) 

        x_reconstr_mean = \
            tf.nn.sigmoid(tf.add(tf.matmul(layer_2, weights['out_mean']), 
                                 biases['out_mean']))

        return x_reconstr_mean

    def _generator_network_no_sigmoid(self, z, weights, biases):

        layer_1 = self.transfer_fct(tf.add(tf.matmul(z, weights['h1']), 
                                           biases['b1'])) 
        layer_2 = self.transfer_fct(tf.add(tf.matmul(layer_1, weights['h2']), 
                                           biases['b2'])) 

        x_reconstr_mean = \
            tf.add(tf.matmul(layer_2, weights['out_mean']), 
                                 biases['out_mean'])

        return x_reconstr_mean
    

    def _log_p_z(self, z):

        #Get log(p(z))
        #This is just exp of standard normal
        # log_p_z = -.5 * tf.matmul(tf.transpose(z), z)  #plus the others terms
        # log_p_z = -.5 * tf.reduce_sum(z**2, 1)  #plus the others terms

        term1 = 0
        term2 = self.network_architecture["n_z"] * tf.log(2*math.pi)
        dif = z
        dif_cov = dif 
        term3 = tf.reduce_sum(dif_cov * dif, 1) #plus other terms TODO

        all_ = term1 + term2 + term3
        log_p_z = -.5 * all_

        return log_p_z

    def _log_p_z_given_x(self, z, mean, log_var_sq):

        #Get log(p(z|x))
        #This is just exp of a normal with some mean and var

        term1 = tf.log(tf.reduce_prod(tf.exp(log_var_sq), reduction_indices=1))
        term2 = self.network_architecture["n_z"] * tf.log(2*math.pi)
        dif = z - mean
        dif_cov = dif / tf.exp(log_var_sq)
        term3 = tf.reduce_sum(dif_cov * dif, 1) #plus other terms TODO

        all_ = term1 + term2 + term3
        log_p_z_given_x = -.5 * all_

        # dist = tf.contrib.distributions.MultivariateNormal(mu=mean, sigma=tf.exp(log_var_sq))
        # log_p_z_given_x = tf.log(dist.pdf(z))

        return log_p_z_given_x


    def _create_loss_optimizer(self):

        recog_mean, recog_log_sigma_sq = self._recognition_network(self.x, self.network_weights["weights_recog"], self.network_weights["biases_recog"])
        self.recog_mean = recog_mean
        self.recog_log_sigma_sq = recog_log_sigma_sq


        reconstr_loss_list = []
        prior_loss_list = []
        recognition_loss_list = []
        for particle in range(self.n_particles):

            eps = tf.random_normal((self.batch_size, self.network_architecture["n_z"]), 0, 1, dtype=tf.float32)
            z = tf.add(recog_mean, tf.mul(tf.sqrt(tf.exp(recog_log_sigma_sq)), eps))

            # log likelihood of coming from prior
            prior_loss = self._log_p_z(z)

            # log likelihood of coming from posterior / recognition
            recognition_loss = self._log_p_z_given_x(z, recog_mean, recog_log_sigma_sq)

            # log likelihood of data
            #Generate frame x_t and Calc reconstruction error
            reconstructed_mean = self._generator_network_no_sigmoid(z, self.network_weights["weights_gener"], self.network_weights["biases_gener"])
            #this sum is over the dimensions 
            reconstr_loss = \
                    -tf.reduce_sum(tf.maximum(reconstructed_mean, 0) 
                                - reconstructed_mean * self.x
                                + tf.log(1 + tf.exp(-abs(reconstructed_mean))),
                                 1)

            prior_loss_list.append(prior_loss)
            recognition_loss_list.append(recognition_loss)
            reconstr_loss_list.append(reconstr_loss)


        prior_loss_tensor = tf.pack(prior_loss_list, axis=1)
        recognition_loss_tensor = tf.pack(recognition_loss_list, axis=1)
        reconstr_loss_tensor = tf.pack(reconstr_loss_list, axis=1)

        self.prior_loss_tensor = tf.pack(prior_loss_list, axis=1)
        self.recognition_loss_tensor = tf.pack(recognition_loss_list, axis=1)
        self.reconstr_loss_tensor = tf.pack(reconstr_loss_list, axis=1)

        # log_w = -prior_loss_tensor + recognition_loss + reconstr_loss #the sums are reversed for some reason
        log_w = tf.add(tf.sub(reconstr_loss_tensor, recognition_loss_tensor),prior_loss_tensor)  #the sums are reversed for some reason
        
        # self.log_w = tf.sub(tf.add(reconstr_loss_tensor, recognition_loss_tensor),prior_loss_tensor)  #the sums are reversed for some reason

        #log mean exp same as log sum exp
        max_ = tf.reduce_max(log_w)

        exp_log_w = tf.exp(log_w - max_)

        #average over particles
        mean_exp_log_w = tf.reduce_mean(exp_log_w, 1)

        mean_log_w = tf.log(mean_exp_log_w) + max_

        # average over batch, take negative because we want to maximize lower bound, minimize negative lower bound
        self.cost = -tf.reduce_mean(mean_log_w)

        # Use ADAM optimizer
        self.optimizer = tf.train.AdamOptimizer(learning_rate=self.learning_rate).minimize(self.cost)
        
    def partial_fit(self, X):
        """Train model based on mini-batch of input data.
        
        Return cost of mini-batch.
        """
        opt, cost = self.sess.run((self.optimizer, self.cost), 
                                  feed_dict={self.x: X})
        return cost
    
    # def transform(self, X):
    #     """Transform data by mapping it into the latent space."""
    #     # Note: This maps to mean of distribution, we could alternatively
    #     # sample from Gaussian distribution
    #     return self.sess.run(self.z_mean, feed_dict={self.x: X})
    
    # def generate(self, z_mu=None):
    #     """ Generate data by sampling from latent space.
        
    #     If z_mu is not None, data for this point in latent space is
    #     generated. Otherwise, z_mu is drawn from prior in latent 
    #     space.        
    #     """
    #     if z_mu is None:
    #         # z_mu = np.random.normal(size=self.network_architecture["n_z"])
    #         z_mu = np.random.normal(size=(self.batch_size, self.network_architecture["n_z"]))

    #     # Note: This maps to mean of distribution, we could alternatively
    #     # sample from Gaussian distribution

    #     return self.sess.run(self.x_reconstr_mean, 
    #                          feed_dict={self.z: z_mu})

    #     # self.z = z_mu
    #     # return self.sess.run(self.x_reconstr_mean)
    
    # def reconstruct(self, X):
    #     """ Use VAE to reconstruct given data. """
    #     return self.sess.run(self.x_reconstr_mean, 
    #                          feed_dict={self.x: X})


    def train(self, train_x, train_y, timelimit=60, max_steps=999, display_step=5):

        n_datapoints = len(train_x)

        start = time.time()
        for step in range(max_steps):

            #Make batch
            batch = []
            while len(batch) != self.batch_size:
                datapoint = train_x[random.randint(0,n_datapoints-1)]
                batch.append(datapoint)

            # Fit training using batch data
            cost = self.partial_fit(batch)

            # self.sess.run(self.check_nan, feed_dict={self.x: batch})
            # test = self.sess.run(self.log_w, feed_dict={self.x: batch})
            # print test

            recog_mean, recog_log_sigma_sq = self.sess.run([self.recog_mean, self.recog_log_sigma_sq], feed_dict={self.x: batch})

            # print
            # print l1
            # print 
            # print l2
            # print 
            # print l3


            print
            print recog_mean
            print 
            print recog_log_sigma_sq


            
            
            # Display logs per epoch step
            if step % display_step == 0:
                print "Step:", '%04d' % (step+1), \
                      "cost=", "{:.9f}".format(cost)

            #Check if time is up
            if time.time() - start > timelimit:
                print 'times up', timelimit
                break


