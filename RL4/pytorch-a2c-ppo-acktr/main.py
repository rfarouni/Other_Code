import copy
import glob
import os
import time

import gym
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.autograd import Variable
from torch.utils.data.sampler import BatchSampler, SubsetRandomSampler

from arguments import get_args
from baselines.common.vec_env.subproc_vec_env import SubprocVecEnv
from envs import make_env
from kfac import KFACOptimizer
from model import CNNPolicy, MLPPolicy
from storage import RolloutStorage
from visualize import visdom_plot

args = get_args()

assert args.algo in ['a2c', 'ppo', 'acktr']
if args.algo == 'ppo':
    assert args.num_processes * args.num_steps % args.batch_size == 0

num_updates = int(args.num_frames) // args.num_steps // args.num_processes

torch.manual_seed(args.seed)
if args.cuda:
    torch.cuda.manual_seed(args.seed)

# try:
#     os.makedirs(args.log_dir)
#     print ('Made dir', args.log_dir)
#     # fsadf
# except OSError:
#     files = glob.glob(os.path.join(args.log_dir, '*.monitor.csv'))
#     for f in files:
#         os.remove(f)


#uncomment this later when you want to save stuff
if not os.path.exists(args.log_dir):
    os.makedirs(args.log_dir)
    print ('Made dir', args.log_dir)
# else:
#     print ('Dir exists')
#     fadfa

def main():
    print("#######")
    print("WARNING: All rewards are clipped so you need to use a monitor (see envs.py) or visdom plot to get true rewards")
    print("#######")

    os.environ['OMP_NUM_THREADS'] = '1'






    print (args.cuda)
    print (args.num_steps)
    print (args.num_processes)
    print (args.lr)
    print (args.eps)
    print (args.alpha)
    print (args.use_gae)
    print (args.gamma)
    print (args.tau)
    print (args.value_loss_coef)
    print (args.entropy_coef)
    fdsafasd

    # if args.vis:
    #     from visdom import Visdom
    #     viz = Visdom()
    #     win = None





    envs = SubprocVecEnv([
        make_env(args.env_name, args.seed, i, args.log_dir)
        for i in range(args.num_processes)
    ])

    # print('here3')
    # fdasf





    obs_shape = envs.observation_space.shape
    obs_shape = (obs_shape[0] * args.num_stack, *obs_shape[1:])

    if len(envs.observation_space.shape) == 3:
        actor_critic = CNNPolicy(obs_shape[0], envs.action_space)
    else:
        actor_critic = MLPPolicy(obs_shape[0], envs.action_space)

    if envs.action_space.__class__.__name__ == "Discrete":
        action_shape = 1
    else:
        action_shape = envs.action_space.shape[0]

    if args.cuda:
        actor_critic.cuda()

    if args.algo == 'a2c':
        optimizer = optim.RMSprop(actor_critic.parameters(), args.lr, eps=args.eps, alpha=args.alpha)
    # elif args.algo == 'ppo':
    #     optimizer = optim.Adam(actor_critic.parameters(), args.lr, eps=args.eps)
    # elif args.algo == 'acktr':
    #     optimizer = KFACOptimizer(actor_critic)








    rollouts = RolloutStorage(args.num_steps, args.num_processes, obs_shape, envs.action_space)
    #it has a self.state that is [steps, processes, obs]
    #steps is used to compute expected reward




    current_state = torch.zeros(args.num_processes, *obs_shape)
    def update_current_state(state):
        shape_dim0 = envs.observation_space.shape[0]
        state = torch.from_numpy(state).float()
        if args.num_stack > 1:
            current_state[:, :-shape_dim0] = current_state[:, shape_dim0:]
        current_state[:, -shape_dim0:] = state

    state = envs.reset()
    update_current_state(state)








    rollouts.states[0].copy_(current_state)
    #set the first state to current state






    # These variables are used to compute average rewards for all processes.
    episode_rewards = torch.zeros([args.num_processes, 1])
    final_rewards = torch.zeros([args.num_processes, 1])

    if args.cuda:
        current_state = current_state.cuda()
        rollouts.cuda()

    # if args.algo == 'ppo':
    #     old_model = copy.deepcopy(actor_critic)

    start = time.time()
    for j in range(num_updates):
        for step in range(args.num_steps):



            # Sample actions
            value, action = actor_critic.act(Variable(rollouts.states[step], volatile=True))
            # make prediction using state that you put into rollouts


            cpu_actions = action.data.squeeze(1).cpu().numpy()
            # Obser reward and next state
            state, reward, done, info = envs.step(cpu_actions)
            # print (state.shape) # [nProcesss, ndims, height, width]
            # fsdf
            reward = torch.from_numpy(np.expand_dims(np.stack(reward), 1)).float()
            episode_rewards += reward

            # If done then clean the history of observations.
            # these final rewards are only used for printing. but the mask is used in the storage, dont know why yet
            # oh its just clearing the env that finished, and resetting its episode_reward
            masks = torch.FloatTensor([[0.0] if done_ else [1.0] for done_ in done]) #if an env is done
            final_rewards *= masks
            final_rewards += (1 - masks) * episode_rewards
            episode_rewards *= masks

            if args.cuda:
                masks = masks.cuda()

            if current_state.dim() == 4:
                current_state *= masks.unsqueeze(2).unsqueeze(2)
            else:
                current_state *= masks

            update_current_state(state)




            rollouts.insert(step, current_state, action.data, value.data, reward, masks)
            # insert all that info into current step
            # not exactly why













        next_value = actor_critic(Variable(rollouts.states[-1], volatile=True))[0].data
        # use last state to make prediction of next value









        if hasattr(actor_critic, 'obs_filter'):
            actor_critic.obs_filter.update(rollouts.states[:-1].view(-1, *obs_shape))
        #not sure what this is








        rollouts.compute_returns(next_value, args.use_gae, args.gamma, args.tau)
        # this computes R =  r + r+ ...+ V(t)  for each step









        if args.algo in ['a2c', 'acktr']:
            values, action_log_probs, dist_entropy = actor_critic.evaluate_actions(Variable(rollouts.states[:-1].view(-1, *obs_shape)), Variable(rollouts.actions.view(-1, action_shape)))
            # I think this aciton log prob could have been computed and stored earlier 
            # and didnt we already store the value prediction???






            values = values.view(args.num_steps, args.num_processes, 1)
            action_log_probs = action_log_probs.view(args.num_steps, args.num_processes, 1)

            advantages = Variable(rollouts.returns[:-1]) - values
            value_loss = advantages.pow(2).mean()

            action_loss = -(Variable(advantages.data) * action_log_probs).mean()

            # if args.algo == 'acktr' and optimizer.steps % optimizer.Ts == 0:
            #     # Sampled fisher, see Martens 2014
            #     actor_critic.zero_grad()
            #     pg_fisher_loss = -action_log_probs.mean()

            #     value_noise = Variable(torch.randn(values.size()))
            #     if args.cuda:
            #         value_noise = value_noise.cuda()

            #     sample_values = values + value_noise
            #     vf_fisher_loss = -(values - Variable(sample_values.data)).pow(2).mean()

            #     fisher_loss = pg_fisher_loss + vf_fisher_loss
            #     optimizer.acc_stats = True
            #     fisher_loss.backward(retain_graph=True)
            #     optimizer.acc_stats = False

            optimizer.zero_grad()
            (value_loss * args.value_loss_coef + action_loss - dist_entropy * args.entropy_coef).backward()

            # if args.algo == 'a2c':
            #     nn.utils.clip_grad_norm(actor_critic.parameters(), args.max_grad_norm)

            optimizer.step()
        # elif args.algo == 'ppo':
        #     advantages = rollouts.returns[:-1] - rollouts.value_preds[:-1]
        #     advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-5)

        #     old_model.load_state_dict(actor_critic.state_dict())
        #     if hasattr(actor_critic, 'obs_filter'):
        #         old_model.obs_filter = actor_critic.obs_filter

        #     for _ in range(args.ppo_epoch):
        #         sampler = BatchSampler(SubsetRandomSampler(range(args.num_processes * args.num_steps)), args.batch_size * args.num_processes, drop_last=False)
        #         for indices in sampler:
        #             indices = torch.LongTensor(indices)
        #             if args.cuda:
        #                 indices = indices.cuda()
        #             states_batch = rollouts.states[:-1].view(-1, *obs_shape)[indices]
        #             actions_batch = rollouts.actions.view(-1, action_shape)[indices]
        #             return_batch = rollouts.returns[:-1].view(-1, 1)[indices]

        #             # Reshape to do in a single forward pass for all steps
        #             values, action_log_probs, dist_entropy = actor_critic.evaluate_actions(Variable(states_batch), Variable(actions_batch))

        #             _, old_action_log_probs, _ = old_model.evaluate_actions(Variable(states_batch, volatile=True), Variable(actions_batch, volatile=True))

        #             ratio = torch.exp(action_log_probs - Variable(old_action_log_probs.data))
        #             adv_targ = Variable(advantages.view(-1, 1)[indices])
        #             surr1 = ratio * adv_targ
        #             surr2 = torch.clamp(ratio, 1.0 - args.clip_param, 1.0 + args.clip_param) * adv_targ
        #             action_loss = -torch.min(surr1, surr2).mean() # PPO's pessimistic surrogate (L^CLIP)

        #             value_loss = (Variable(return_batch) - values).pow(2).mean()

        #             optimizer.zero_grad()
        #             (value_loss + action_loss - dist_entropy * args.entropy_coef).backward()
        #             optimizer.step()




        rollouts.states[0].copy_(rollouts.states[-1])
        # the first state is now the last state of the previous 









        # if j % args.save_interval == 0 and args.save_dir != "":
        #     save_path = os.path.join(args.save_dir, args.algo)
        #     try:
        #         os.makedirs(save_path)
        #     except OSError:
        #         pass

        #     # A really ugly way to save a model to CPU
        #     save_model = actor_critic
        #     if args.cuda:
        #         save_model = copy.deepcopy(actor_critic).cpu()
        #     torch.save(save_model, os.path.join(save_path, args.env_name + ".pt"))

        if j % args.log_interval == 0:
            end = time.time()
            total_num_steps = (j + 1) * args.num_processes * args.num_steps
            print("Updates {}, num timesteps {}, FPS {}, mean/median reward {:.1f}/{:.1f}, min/max reward {:.1f}/{:.1f}, entropy {:.5f}, value loss {:.5f}, policy loss {:.5f}".
                format(j, total_num_steps,
                       int(total_num_steps / (end - start)),
                       final_rewards.mean(),
                       final_rewards.median(),
                       final_rewards.min(),
                       final_rewards.max(), -dist_entropy.data[0],
                       value_loss.data[0], action_loss.data[0]))

        # if j % args.vis_interval == 0:
        #     win = visdom_plot(viz, win, args.log_dir, args.env_name, args.algo)


if __name__ == "__main__":
    main()