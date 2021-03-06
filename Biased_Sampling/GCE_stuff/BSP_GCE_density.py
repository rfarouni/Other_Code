


import tensorflow as tf
import numpy as np
import random

import cPickle, gzip

import BSP_GCE_tools as tools

import pickle

from sklearn.neighbors.kde import KernelDensity
from sklearn.decomposition import PCA


# Load the dataset
f = gzip.open('mnist.pkl.gz', 'rb')
train_set, valid_set, test_set = cPickle.load(f)
f.close()


train_x = train_set[0]
train_y = tools.convert_array_to_one_hot_matrix(train_set[1])
valid_x = valid_set[0]
valid_y = tools.convert_array_to_one_hot_matrix(valid_set[1])
test_x = test_set[0]
test_y = tools.convert_array_to_one_hot_matrix(test_set[1])

print 'Training set ' +  str(train_x.shape)
print tools.class_counter(train_y)
print
print 'Validation set ' +  str(valid_x.shape)
print tools.class_counter(valid_y)
print
print 'Test set ' +  str(test_x.shape)
print tools.class_counter(test_y) 
print


# Parameters
lr = .0001
mom = .9
tol = .1
batch_size = 1000


# Network Parameters
n_input = 784 # MNIST data input (img shape: 28*28)
n_hidden_1 = 100 # 1st layer num features
n_classes = 10 # MNIST total classes (0-9 digits)

#Define variables
weights = 	{
				'h1': tf.Variable(tf.random_normal([n_input, n_hidden_1])),
				'out': tf.Variable(tf.random_normal([n_hidden_1, n_classes]))
			}
biases = 	{
				'b1': tf.Variable(tf.random_normal([n_hidden_1])),
				'out': tf.Variable(tf.random_normal([n_classes]))
			}

def model(_X, _weights, _biases):
	#Hidden layer with RELU activation
	layer_1 = tf.nn.relu(tf.add(tf.matmul(_X, _weights['h1']), _biases['b1'])) 
	return tf.nn.softmax(tf.matmul(layer_1, weights['out']) + biases['out'])


x = tf.placeholder("float", shape=[None, 784])
y_ = tf.placeholder("float", shape=[None, 10])
samps_densities = tf.placeholder("float", shape=[None])

y = model(x,weights,biases)
cross_entropy = -tf.reduce_sum(tf.matmul(tf.diag(samps_densities),y_*tf.log(tf.clip_by_value(y,1e-10,1.0))))

opt = tf.train.MomentumOptimizer(lr, mom)
grads_and_vars = opt.compute_gradients(cross_entropy)
modified_grad_and_vars = [(gv[0], gv[1]) for gv in grads_and_vars]
apply_grad = opt.apply_gradients(modified_grad_and_vars)

correct_prediction = tf.equal(tf.argmax(y,1), tf.argmax(y_,1))
accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))

bias_set = [.5, .6, .7, .8, .9]
reps = 10

result_store = []

#repeat and average
for rep in range(reps):

	result_store.append([])

	#for different amounts of bias
	for bias in bias_set:

		print '\nBias ' + str(bias) + ' Rep ' + str(rep)

		#Shuffle data
		indexes = random.sample(range(len(train_y)), len(train_y))
		train_x = train_x[indexes]
		train_y = train_y[indexes]

		#Modify the training set and validaation set
		train_x_alt, train_y_alt = tools.bias_sampling3(train_x, train_y, bias, 25000)
		print 'Training set ' +  str(train_x_alt.shape)
		print tools.class_counter(train_y_alt)

		valid_x_alt, valid_y_alt = tools.bias_sampling3(valid_x, valid_y, bias, 5000)
		print 'Validation set ' +  str(valid_x_alt.shape)
		print tools.class_counter(valid_y_alt)

		#Pick some background samps
		indexes = random.sample(range(len(valid_y)), 1000)
		background_samps = train_x[indexes]
		background_target = train_y[indexes]

		pca = PCA(n_components=20)
		pca.fit(background_samps)
		b_samps_pca = pca.transform(background_samps)

		#Fit density model
		kde = KernelDensity(kernel='gaussian', bandwidth=.5).fit(b_samps_pca)

		train_x_alt_pca = pca.transform(train_x_alt)
		valid_x_alt_pca = pca.transform(valid_x_alt)

		density_train = kde.score_samples(train_x_alt_pca)
		density_valid = kde.score_samples(valid_x_alt_pca)

		#get min density then put the over 1
		min_density = np.min(density_train)
		
		density_train = density_train - min_density + 1.
		mean_density = np.mean(density_train)
		density_train = density_train / mean_density

		density_valid = density_valid - min_density + 1.
		density_valid = density_valid / mean_density

		# print density_train[:10]
		# fasfd

		density_train = np.reciprocal(density_train)
		density_valid = np.reciprocal(density_valid)


		early_stop_count = 0
		best_valid_ce = -1
		train_acc = -1
		valid_acc = -1
		test_acc = -1
		cur_ind = 0

		# sess = tf.Session()
		with tf.Session() as sess:
		
			sess.run(tf.initialize_all_variables())

			for iter_ in range(999999):		

				#print status
				if iter_ % (100000/batch_size) == 0:
					print sess.run(accuracy, feed_dict={x: train_x_alt, y_: train_y_alt}), tools.class_counter(sess.run(y, feed_dict={x: train_x_alt, y_: train_y_alt}))
					print sess.run(accuracy, feed_dict={x: valid_x_alt, y_: valid_y_alt}), tools.class_counter(sess.run(y, feed_dict={x: valid_x_alt, y_: valid_y_alt}))
					print sess.run(accuracy, feed_dict={x: test_x, y_: test_y}), tools.class_counter(sess.run(y, feed_dict={x: test_x, y_: test_y}))


				#check for convergence
				if iter_ % (10000/batch_size) == 0:
					valid_ce = sess.run(cross_entropy, feed_dict={x: valid_x_alt, y_: valid_y_alt, samps_densities: density_valid})
					print iter_, valid_ce

					if best_valid_ce - valid_ce < tol and best_valid_ce != -1:
						early_stop_count += 1
						print 'early stop count ' + str(early_stop_count)
						if early_stop_count == 20:
							print 'Converged'
							
							print 'train acc ' + str(train_acc)
							print tools.class_counter(sess.run(y, feed_dict={x: train_x_alt, y_: train_y_alt}))
							
							print 'valid acc ' + str(valid_acc)
							print tools.class_counter(sess.run(y, feed_dict={x: valid_x_alt, y_: valid_y_alt}))
							
							print 'test acc ' + str(test_acc)
							print tools.class_counter(sess.run(y, feed_dict={x: test_x, y_: test_y}))

							result_store[rep].append([train_acc, valid_acc, test_acc])

							break
					else:
						early_stop_count = 0

					if best_valid_ce > valid_ce or best_valid_ce == -1:
						best_valid_ce = valid_ce

						train_acc = sess.run(accuracy, feed_dict={x: train_x_alt, y_: train_y_alt})
						valid_acc = sess.run(accuracy, feed_dict={x: valid_x_alt, y_: valid_y_alt})
						test_acc = sess.run(accuracy, feed_dict={x: test_x, y_: test_y})			

				batch, indexes_ = tools.next_batch_and_return_indexes(train_x_alt, train_y_alt, batch_size)
				batch_densitities = density_train[indexes_]

				_ = sess.run([apply_grad], feed_dict={x: batch[0], y_: batch[1], samps_densities: batch_densitities})



#save results
with open('results_densities2_10.pkl', "wb" ) as f:
	pickle.dump(result_store, f)
	print 'saved results'





