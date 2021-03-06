


# take in dict

# add ppo

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torch.optim.lr_scheduler as lr_scheduler
from torch.autograd import Variable
from torch.utils.data.sampler import BatchSampler, SubsetRandomSampler

import copy
from kfac import KFACOptimizer
from model import CNNPolicy, MLPPolicy, CNNPolicy_dropout, CNNPolicy2, CNNPolicy_dropout2
from storage import RolloutStorage








class a2c(object):

    def __init__(self, envs, hparams):

        self.use_gae = hparams['use_gae']
        self.gamma = hparams['gamma']
        self.tau = hparams['tau']

        self.obs_shape = hparams['obs_shape']
        self.num_steps = hparams['num_steps']
        self.num_processes = hparams['num_processes']
        self.value_loss_coef = hparams['value_loss_coef']
        self.entropy_coef = hparams['entropy_coef']
        self.cuda = hparams['cuda']
        self.opt = hparams['opt']



        if hparams['dropout'] == True:
            print ('CNNPolicy_dropout')
            actor_critic = CNNPolicy_dropout2(self.obs_shape[0], envs.action_space)
            # actor_critic = CNNPolicy_dropout(self.obs_shape[0], envs.action_space)
        elif len(envs.observation_space.shape) == 3:
            print ('CNNPolicy')
            actor_critic = CNNPolicy2(self.obs_shape[0], envs.action_space)
            # actor_critic = CNNPolicy(self.obs_shape[0], envs.action_space)
        else:
            actor_critic = MLPPolicy(self.obs_shape[0], envs.action_space)

        if envs.action_space.__class__.__name__ == "Discrete":
            action_shape = 1
        else:
            action_shape = envs.action_space.shape[0]
        self.action_shape = action_shape

        rollouts = RolloutStorage(self.num_steps, self.num_processes, self.obs_shape, envs.action_space)
        #it has a self.state that is [steps, processes, obs]
        #steps is used to compute expected reward

        if self.cuda:
            actor_critic.cuda()
            rollouts.cuda()

        if self.opt == 'rms':
            self.optimizer = optim.RMSprop(params=actor_critic.parameters(), lr=hparams['lr'], eps=hparams['eps'], alpha=hparams['alpha'])
        elif self.opt == 'adam':
            self.optimizer = optim.Adam(params=actor_critic.parameters(), lr=hparams['lr'], eps=hparams['eps'])
        else:
            print ('no opt specified')

        self.actor_critic = actor_critic
        self.rollouts = rollouts



    def act(self, current_state):

        # Sample actions
        value, action = self.actor_critic.act(current_state)
        # make prediction using state that you put into rollouts


        return action, value


    def insert_first_state(self, current_state):

        self.rollouts.states[0].copy_(current_state)
        #set the first state to current state




    def insert_data(self, step, current_state, action, value, reward, masks):

        self.rollouts.insert(step, current_state, action, value, reward, masks)
        # insert all that info into current step
        # not exactly why




    def update(self):
        
        next_value = self.actor_critic(Variable(self.rollouts.states[-1], volatile=True))[0].data
        # use last state to make prediction of next value
        #isnt [0] the action prediction?? not value??, no its [1]
        # print('update value', next_value)
        # # fsadfa
        # print (self.actor_critic(Variable(self.rollouts.states[-1], volatile=True)))
        # print()
        #not the same as act.


        # if hasattr(self.actor_critic, 'obs_filter'):
        #     self.actor_critic.obs_filter.update(self.rollouts.states[:-1].view(-1, *obs_shape))
        #not sure what this is




        self.rollouts.compute_returns(next_value, self.use_gae, self.gamma, self.tau)
        # this computes R =  r + r+ ...+ V(t)  for each step



        values, action_log_probs, dist_entropy = self.actor_critic.evaluate_actions(
                                                    Variable(self.rollouts.states[:-1].view(-1, *self.obs_shape)), 
                                                    Variable(self.rollouts.actions.view(-1, self.action_shape)))
        # I think this aciton log prob could have been computed and stored earlier 
        # and didnt we already store the value prediction???
        # ya could totally store this info sooner
        #might not work for ppo
        # if I move it then it reduces amount of computation, because it doesnt need to go through agent again
        #but it increases memeory because I need to store it
        #if the model was large, this could be a significant cost
        #and storing the log probs and entropy isnt a huge amount


        values = values.view(self.num_steps, self.num_processes, 1)
        action_log_probs = action_log_probs.view(self.num_steps, self.num_processes, 1)

        advantages = Variable(self.rollouts.returns[:-1]) - values
        value_loss = advantages.pow(2).mean()

        action_loss = -(Variable(advantages.data) * action_log_probs).mean()

        self.optimizer.zero_grad()
        cost = action_loss + value_loss*self.value_loss_coef - dist_entropy*self.entropy_coef
        cost.backward()

        nn.utils.clip_grad_norm(self.actor_critic.parameters(), .5)


        self.optimizer.step()




















class ppo(object):


    def __init__(self, envs, hparams):

        self.use_gae = hparams['use_gae']
        self.gamma = hparams['gamma']
        self.tau = hparams['tau']

        self.obs_shape = hparams['obs_shape']
        self.num_steps = hparams['num_steps']
        self.num_processes = hparams['num_processes']
        self.value_loss_coef = hparams['value_loss_coef']
        self.entropy_coef = hparams['entropy_coef']
        self.cuda = hparams['cuda']
        self.ppo_epoch = hparams['ppo_epoch']
        self.batch_size = hparams['batch_size']
        self.clip_param = hparams['clip_param']



        if len(envs.observation_space.shape) == 3:
            actor_critic = CNNPolicy(self.obs_shape[0], envs.action_space)
        else:
            actor_critic = MLPPolicy(self.obs_shape[0], envs.action_space)

        if envs.action_space.__class__.__name__ == "Discrete":
            action_shape = 1
        else:
            action_shape = envs.action_space.shape[0]
        self.action_shape = action_shape

        rollouts = RolloutStorage(self.num_steps, self.num_processes, self.obs_shape, envs.action_space)
        #it has a self.state that is [steps, processes, obs]
        #steps is used to compute expected reward

        if self.cuda:
            actor_critic.cuda()
            rollouts.cuda()

        self.eps = hparams['eps']

        # self.optimizer = optim.RMSprop(params=actor_critic.parameters(), lr=hparams['lr'], eps=hparams['eps'], alpha=hparams['alpha'])
        self.optimizer = optim.Adam(params=actor_critic.parameters(), lr=hparams['lr'], eps=hparams['eps'])

        # if hparams['lr_schedule'] == 'linear':
        self.init_lr = hparams['lr']
        self.final_lr = hparams['final_lr']
        #     lr_func = lambda epoch: max( init_lr*(1.-(epoch/500.)), final_lr)
        #     self.optimizer2 = lr_scheduler.LambdaLR(self.optimizer, lr_lambda=lr_func)
        # self.current_lr = hparams['lr']


        self.actor_critic = actor_critic
        self.rollouts = rollouts


        self.old_model = copy.deepcopy(self.actor_critic)



    def act(self, current_state):

        # Sample actions
        value, action = self.actor_critic.act(current_state)
        # make prediction using state that you put into rollouts


        return action, value


    def insert_first_state(self, current_state):

        self.rollouts.states[0].copy_(current_state)
        #set the first state to current state




    def insert_data(self, step, current_state, action, value, reward, masks):

        self.rollouts.insert(step, current_state, action, value, reward, masks)
        # insert all that info into current step
        # not exactly why




    def update(self, step=-1, max_steps=-1):
        
        next_value = self.actor_critic(Variable(self.rollouts.states[-1], volatile=True))[0].data
        # use last state to make prediction of next value



        # if hasattr(self.actor_critic, 'obs_filter'):
        #     self.actor_critic.obs_filter.update(self.rollouts.states[:-1].view(-1, *self.obs_shape))
        # #not sure what this is




        self.rollouts.compute_returns(next_value, self.use_gae, self.gamma, self.tau)
        # this computes R =  r + r+ ...+ V(t)  for each step



        advantages = self.rollouts.returns[:-1] - self.rollouts.value_preds[:-1]
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-5)

        self.old_model.load_state_dict(self.actor_critic.state_dict())


        # if hasattr(self.actor_critic, 'obs_filter'):
        #     self.old_model.obs_filter = self.actor_critic.obs_filter


        for _ in range(self.ppo_epoch): #number of grad steps
            # [0...P*S] are the indices of the data
            # Then seperate the data into batches, where batch size = batch_size*P 
            # so length of sampler is S/P = num_steps / batch_size 
            sampler = BatchSampler(SubsetRandomSampler(range(self.num_processes * self.num_steps)), self.batch_size * self.num_processes, drop_last=True)
            # print (np.array(list(sampler)).shape)
            # fda
            for indices in sampler:
                indices = torch.LongTensor(indices)
                if self.cuda:
                    indices = indices.cuda()
                states_batch = self.rollouts.states[:-1].view(-1, *self.obs_shape)[indices]
                actions_batch = self.rollouts.actions.view(-1, self.action_shape)[indices]
                return_batch = self.rollouts.returns[:-1].view(-1, 1)[indices]
                adv_targ = Variable(advantages.view(-1, 1)[indices])

                # Reshape to do in a single forward pass for all steps
                values, action_log_probs, dist_entropy = self.actor_critic.evaluate_actions(Variable(states_batch), Variable(actions_batch))

                _, old_action_log_probs, _ = self.old_model.evaluate_actions(Variable(states_batch, volatile=True), Variable(actions_batch, volatile=True))

                # ratio = torch.exp(action_log_probs - Variable(old_action_log_probs.data))
                # adv_targ = Variable(advantages.view(-1, 1)[indices])
                # surr1 = ratio * adv_targ
                # surr2 = torch.clamp(ratio, 1.0 - self.clip_param, 1.0 + self.clip_param) * adv_targ
                # action_loss = -torch.min(surr1, surr2).mean() # PPO's pessimistic surrogate (L^CLIP)

                ratio = torch.exp(action_log_probs - Variable(old_action_log_probs.data))
                ratio_clamped = torch.clamp(ratio, 1.0 - self.clip_param, 1.0 + self.clip_param)

                surr1 = ratio * adv_targ
                surr2 = ratio_clamped * adv_targ
                action_loss = -torch.min(surr1, surr2).mean() # PPO's pessimistic surrogate (L^CLIP)

                value_loss = (Variable(return_batch) - values).pow(2).mean()


                self.current_lr = max(self.init_lr*(1.-(step/1000.)), self.final_lr)
                self.optimizer = optim.Adam(params=self.actor_critic.parameters(), lr=self.current_lr, eps=self.eps)


                self.optimizer.zero_grad()
                cost = action_loss + value_loss*self.value_loss_coef - dist_entropy*self.entropy_coef
                cost.backward()
                self.optimizer.step()

                
























class a2c_minibatch(object):

    def __init__(self, envs, hparams):

        self.use_gae = hparams['use_gae']
        self.gamma = hparams['gamma']
        self.tau = hparams['tau']

        self.obs_shape = hparams['obs_shape']
        self.num_steps = hparams['num_steps']
        self.num_processes = hparams['num_processes']
        self.value_loss_coef = hparams['value_loss_coef']
        self.entropy_coef = hparams['entropy_coef']
        self.cuda = hparams['cuda']
        self.opt = hparams['opt']
        self.batch_size = hparams['batch_size']
        self.a2c_epochs = hparams['a2c_epochs']







        if len(envs.observation_space.shape) == 3:
            actor_critic = CNNPolicy(self.obs_shape[0], envs.action_space)
        else:
            actor_critic = MLPPolicy(self.obs_shape[0], envs.action_space)

        if envs.action_space.__class__.__name__ == "Discrete":
            action_shape = 1
        else:
            action_shape = envs.action_space.shape[0]
        self.action_shape = action_shape

        rollouts = RolloutStorage(self.num_steps, self.num_processes, self.obs_shape, envs.action_space)
        #it has a self.state that is [steps, processes, obs]
        #steps is used to compute expected reward

        if self.cuda:
            actor_critic.cuda()
            rollouts.cuda()

        if self.opt == 'rms':
            self.optimizer = optim.RMSprop(params=actor_critic.parameters(), lr=hparams['lr'], eps=hparams['eps'], alpha=hparams['alpha'])
        elif self.opt == 'adam':
            self.optimizer = optim.Adam(params=actor_critic.parameters(), lr=hparams['lr'], eps=hparams['eps'])
        else:
            print ('no opt specified')

        self.actor_critic = actor_critic
        self.rollouts = rollouts



    def act(self, current_state):
        value, action = self.actor_critic.act(current_state)
        return action, value


    def insert_first_state(self, current_state):
        self.rollouts.states[0].copy_(current_state)


    def insert_data(self, step, current_state, action, value, reward, masks):
        self.rollouts.insert(step, current_state, action, value, reward, masks)


    def update(self):
        
        next_value = self.actor_critic(Variable(self.rollouts.states[-1], volatile=True))[0].data
        self.rollouts.compute_returns(next_value, self.use_gae, self.gamma, self.tau)
        advantages = self.rollouts.returns[:-1] - self.rollouts.value_preds[:-1]

        for _ in range(self.a2c_epochs):
            sampler = BatchSampler(SubsetRandomSampler(range(self.num_processes * self.num_steps)), self.batch_size * self.num_processes, drop_last=True)
            for indices in sampler:
                indices = torch.LongTensor(indices)
                if self.cuda:
                    indices = indices.cuda()
                states_batch = self.rollouts.states[:-1].view(-1, *self.obs_shape)[indices]
                actions_batch = self.rollouts.actions.view(-1, self.action_shape)[indices]
                return_batch = self.rollouts.returns[:-1].view(-1, 1)[indices]
                adv_targ = Variable(advantages.view(-1, 1)[indices])

                values, action_log_probs, dist_entropy = self.actor_critic.evaluate_actions(Variable(states_batch), Variable(actions_batch))

                value_loss = adv_targ.pow(2).mean()

                action_loss = -(adv_targ * action_log_probs).mean()

                self.optimizer.zero_grad()
                cost = action_loss + value_loss*self.value_loss_coef - dist_entropy*self.entropy_coef
                cost.backward()
                self.optimizer.step()













