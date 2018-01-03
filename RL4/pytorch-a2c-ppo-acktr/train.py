

import sys
# print (sys.path)
for i in range(len(sys.path)):
    if 'ccremer/Documents' in sys.path[i]:
        # print (sys.path[i])
        # print (i)
        sys.path.remove(sys.path[i])#[i]
        break
# print (sys.path)



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

sys.path.insert(0, './baselines/')
sys.path.insert(0, './baselines/baselines/common/vec_env')
# from baselines.baselines.common.vec_env.subproc_vec_env import SubprocVecEnv
from subproc_vec_env import SubprocVecEnv
# import baselines.baselines.common.vec_env.subproc_vec_env
# print (baselines.common.vec_env.subproc_vec_env.__file__)
# print (SubprocVecEnv)
# fasdfd

from envs import make_env
from envs import make_env_monitor
from envs import make_both_env_types

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


from agent_modular2 import a2c
from agent_modular2 import ppo
from agent_modular2 import a2c_minibatch


from make_plots import make_plots

import argparse
import json
import subprocess

# from arguments import get_args
parser = argparse.ArgumentParser()
parser.add_argument('--m')
args = parser.parse_args()
# print (args.m)


with open(args.m, 'r') as infile:
    model_dict = json.load(infile)

# print (model_dict)


def train(model_dict):

    def update_current_state(current_state, state, channels):
        # current_state: [processes, channels*stack, height, width]
        state = torch.from_numpy(state).float()  # (processes, channels, height, width)
        # if num_stack > 1:
        #first stack*channel-channel frames = last stack*channel-channel , so slide them forward
        current_state[:, :-channels] = current_state[:, channels:] 
        current_state[:, -channels:] = state #last frame is now the new one
        return current_state


    def update_rewards(reward, done, final_rewards, episode_rewards, current_state):
        # Reward, Done: [P], [P]
        # final_rewards, episode_rewards: [P,1]. [P,1]
        # current_state: [P,C*S,H,W]
        reward = torch.from_numpy(np.expand_dims(np.stack(reward), 1)).float() #[P,1]
        episode_rewards += reward #keeps track of current episode cumulative reward
        masks = torch.FloatTensor([[0.0] if done_ else [1.0] for done_ in done]) #[P,1]
        final_rewards *= masks #erase the ones that are done
        final_rewards += (1 - masks) * episode_rewards  #set it to the cumulative episode reward
        episode_rewards *= masks #erase the done ones
        masks = masks.type(dtype) #cuda
        if current_state.dim() == 4:  # if state is a frame/image
            current_state *= masks.unsqueeze(2).unsqueeze(2)  #[P,1,1,1]
        else:
            current_state *= masks   #restart the done ones, by setting the state to zero
        return reward, masks, final_rewards, episode_rewards, current_state

    def do_vid():
        n_vids=3
        for i in range(n_vids):
            done=False
            state = envs_video.reset()
            # state = torch.from_numpy(state).float().type(dtype)
            current_state = torch.zeros(1, *obs_shape)
            current_state = update_current_state(current_state, state, shape_dim0).type(dtype)
            # print ('Recording')
            # count=0
            while not done:
                # print (count)
                # count +=1
                # Act
                state_var = Variable(current_state, volatile=True) 
                # print (state_var.size())
                action, value = agent.act(state_var)
                cpu_actions = action.data.squeeze(1).cpu().numpy()

                # Observe reward and next state
                state, reward, done, info = envs_video.step(cpu_actions) # state:[nProcesss, ndims, height, width]
                # state = torch.from_numpy(state).float().type(dtype)
                # current_state = torch.zeros(1, *obs_shape)
                current_state = update_current_state(current_state, state, shape_dim0).type(dtype)
        state = envs_video.reset()
        
        vid_path = save_dir+'/videos/'
        count =0
        for aaa in os.listdir(vid_path):

            if 'openaigym' in aaa and '.mp4' in aaa:
                #os.rename(vid_path+aaa, vid_path+'vid_t'+str(total_num_steps)+'.mp4')
                subprocess.call("(cd "+vid_path+" && mv "+ vid_path+aaa +" "+ vid_path+env_name+'_'+algo+'_vid_t'+str(total_num_steps)+'_'+str(count) +".mp4)", shell=True) 
                count+=1
            if '.json' in aaa:
                os.remove(vid_path+aaa)

    def save_frame(state, count):

        frame_path = save_dir+'/frames/'
        if not os.path.exists(frame_path):
            os.makedirs(frame_path)
            print ('Made dir', frame_path) 

        state1 = np.squeeze(state[0])
        # print (state1.shape)
        fig = plt.figure(figsize=(4,4), facecolor='white')
        plt.imshow(state1, cmap='gray')
        plt.savefig(frame_path+'frame' +str(count)+'.png')
        print ('saved',frame_path+'frame' +str(count)+'.png')
        plt.close(fig)
        # fasdfa



    # def do_view_envs():
    #     n_steps = 3
    #     state = env_modified.reset()
    #     current_state = torch.zeros(1, *obs_shape)
    #     current_state = update_current_state(current_state, state, shape_dim0).type(dtype)
    #     current_state = Variable(current_state, volatile=True) 
    #     for i in range(n_steps):

    #         # print (state_var.size())
    #         action, value = agent.act(current_state)
    #         cpu_actions = action.data.squeeze(1).cpu().numpy()
    #         # Observe reward and next state
    #         state, reward, done, info = env_modified.step(cpu_actions) # state:[nProcesss, ndims, height, width]
    #         state = env_modified.render(mode='rgb_array')
    #         print(state.shape)

    #         fdsafa

    #         # state = torch.from_numpy(state).float().type(dtype)
    #         # current_state = torch.zeros(1, *obs_shape)
    #         current_state = update_current_state(current_state, state, shape_dim0).type(dtype)




    num_frames = model_dict['num_frames']
    cuda = model_dict['cuda']
    which_gpu = model_dict['which_gpu']
    num_steps = model_dict['num_steps']
    num_processes = model_dict['num_processes']
    seed = model_dict['seed']
    env_name = model_dict['env']
    save_dir = model_dict['save_to']
    num_stack = model_dict['num_stack']
    algo = model_dict['algo']
    save_interval = model_dict['save_interval']
    log_interval = model_dict['log_interval']

    # print("#######")
    # print("WARNING: All rewards are clipped so you need to use a monitor (see envs.py) or visdom plot to get true rewards")
    # print("#######")

    os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['CUDA_VISIBLE_DEVICES'] = str(which_gpu)

    num_updates = int(num_frames) // num_steps // num_processes

    
    if cuda:
        torch.cuda.manual_seed(seed)
    else:
        torch.manual_seed(seed)


    # Create environments
    print (num_processes, 'processes')
    envs = SubprocVecEnv([make_env(env_name, seed, i, save_dir) for i in range(num_processes)])


    vid_ = 1

    if vid_:
        print ('env for video')
        # envs_video = gym.make(env_name)
        # envs_video = gym.wrappers.Monitor(envs_video, save_dir+'/videos/', video_callable=lambda x: True, force=True)
        envs_video = make_env_monitor(env_name, save_dir)#+'/videos/')

    # print ('envs for seeing modified and un-modified rewards and states')
    # env_real, env_modified = make_both_env_types(env_name)


    obs_shape = envs.observation_space.shape  # (channels, height, width)
    obs_shape = (obs_shape[0] * num_stack, *obs_shape[1:])  # (channels*stack, height, width)
    shape_dim0 = envs.observation_space.shape[0]  #channels

    model_dict['obs_shape']=obs_shape

    if cuda:
        dtype = torch.cuda.FloatTensor
    else:
        dtype = torch.FloatTensor


    # Create agent
    if algo == 'a2c':
        agent = a2c(envs, model_dict)
    elif algo == 'ppo':
        agent = ppo(envs, model_dict)
    elif algo == 'a2c_minibatch':
        agent = a2c_minibatch(envs, model_dict)

    # #Load model
    # if args.load_path != '':
    #     # agent.actor_critic = torch.load(os.path.join(args.load_path))
    #     agent.actor_critic = torch.load(args.load_path).cuda()
    #     print ('loaded ', args.load_path)

    # Init state
    state = envs.reset()  # (processes, channels, height, width)
    current_state = torch.zeros(num_processes, *obs_shape)  # (processes, channels*stack, height, width)
    current_state = update_current_state(current_state, state, shape_dim0).type(dtype) #add the new frame, remove oldest
    agent.insert_first_state(current_state) #storage has states: (num_steps + 1, num_processes, *obs_shape), set first step 

    # These are used to compute average rewards for all processes.
    episode_rewards = torch.zeros([num_processes, 1]) #keeps track of current episode cumulative reward
    final_rewards = torch.zeros([num_processes, 1])


    # do_view_envs()
    # fadasd

    #Begin training
    count =0
    start = time.time()
    for j in range(num_updates):
        for step in range(num_steps):

            # Act, [P,1], [P,1]
            action, value = agent.act(Variable(agent.rollouts.states[step], volatile=True))
            cpu_actions = action.data.squeeze(1).cpu().numpy() #[P]

            # Step, S:[P,C,H,W], R:[P], D:[P]
            state, reward, done, info = envs.step(cpu_actions) 



            # save_frame(state, count)
            # count+=1
            # if done[0]:
            #     ffsdfa

            # state = envs.render()
            # print(state.shape)
            # fdsafa

            # Record rewards
            reward, masks, final_rewards, episode_rewards, current_state = update_rewards(reward, done, final_rewards, episode_rewards, current_state)
            
            # Update state, I think this should go before record rewards, because its adding the last state
                # of the previous episode to the done current_states, ie I just set them to 0
                #unless the last state is really the first of the next episode, but I doubt it.
            current_state = update_current_state(current_state, state, shape_dim0)

            # Agent record step, just saves all those values, I think this should go before record rewards too
                #but just need to change some numpy to pytorch 
            # Issue could be the mask, it needs to be updated before this .
            agent.insert_data(step, current_state, action.data, value.data, reward, masks)

            # print (step, 'value_preds', agent.rollouts.value_preds.cpu().numpy().reshape(6,2))
            # self.rewards = self.rewards.cuda()
            # self.value_preds = self.value_preds.cuda()
            # self.returns = self.returns.cuda()

        #Optimize agent
        agent.update()
        agent.insert_first_state(agent.rollouts.states[-1])







        total_num_steps = (j + 1) * num_processes * num_steps

        #Save model
        if total_num_steps % save_interval == 0 and save_dir != "":
            save_path = os.path.join(save_dir, 'model_params')
            try:
                os.makedirs(save_path)
            except OSError:
                pass
            # A really ugly way to save a model to CPU
            save_model = agent.actor_critic
            if cuda:
                save_model = copy.deepcopy(agent.actor_critic).cpu()
            # torch.save(save_model, os.path.join(save_path, args.env_name + ".pt"))
            save_to=os.path.join(save_path, "model_params" + str(total_num_steps)+".pt")
            torch.save(save_model, save_to)
            print ('saved', save_to)

            #make video
            if vid_:
                do_vid()


        #Print updates
        if j % log_interval == 0:
            end = time.time()

            if j % (log_interval*30) == 0:

                #update plots
                try:
                    make_plots(model_dict)
                    print("Upts, n_timesteps, min/med/mean/max, FPS, Time, Plot updated")
                except:
                    print("Upts, n_timesteps, min/med/mean/max, FPS, Time")

            print("{}, {}, {:.1f}/{:.1f}/{:.1f}/{:.1f}, {}, {:.1f}".
                    format(j, total_num_steps,
                           final_rewards.min(),
                           final_rewards.median(),
                           final_rewards.mean(),
                           final_rewards.max(),
                           int(total_num_steps / (end - start)),
                           end - start))

    
    try:
        make_plots(model_dict)
    except:
        print ()
        # pass #raise



if __name__ == "__main__":
    train(model_dict)




