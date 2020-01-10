#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Nov 12 17:39:17 2019

@author: molano


Perceptual decision-making task, based on

  Bounded integration in parietal cortex underlies decisions even when viewing
  duration is dictated by the environment.
  R Kiani, TD Hanks, & MN Shadlen, JNS 2008.

  http://dx.doi.org/10.1523/JNEUROSCI.4761-07.2008

  But allowing for more than 2 choices.

"""

import neurogym as ngym
from neurogym.ops import tasktools
import numpy as np
from gym import spaces
import matplotlib.pyplot as plt


class nalt_RDM(ngym.Env):
    def __init__(self, dt=100, timing=(500, 80, 330, 1500, 500), stimEv=1.,
                 n_ch=3, **kwargs):
        super().__init__(dt=dt)
        self.n = n_ch
        self.choices = np.arange(n_ch) + 1
        # cohs specifies the amount of evidence (which is modulated by stimEv)
        self.cohs = np.array([0, 6.4, 12.8, 25.6, 51.2])*stimEv
        # Input noise
        self.sigma = np.sqrt(2*100*0.01)
        self.sigma_dt = self.sigma / np.sqrt(self.dt)
        # Durations (stimulus duration will be drawn from an exponential)
        # TODO: this is not natural
        self.fixation = timing[0]
        self.stimulus_min = timing[1]
        self.stimulus_mean = timing[2]
        self.stimulus_max = timing[3]
        self.decision = timing[4]
        self.mean_trial_duration = self.fixation + self.stimulus_mean +\
            self.decision
        # TODO: How to make this easier?
        self.max_trial_duration = self.fixation + self.stimulus_max +\
            self.decision
        self.max_steps = int(self.max_trial_duration/dt)

        # Rewards
        self.R_ABORTED = -0.1
        self.R_CORRECT = +1.
        self.R_FAIL = 0.
        self.R_MISS = 0.
        self.abort = False
        # action and observation spaces
        self.stimulus_min = np.max([self.stimulus_min, dt])
        self.action_space = spaces.Discrete(n_ch+1)
        self.observation_space = spaces.Box(-np.inf, np.inf, shape=(n_ch+1,),
                                            dtype=np.float32)
        # seeding
        self.seed()
        self.viewer = None

    def __str__(self):
        string = ''
        if (self.fixation == 0 or self.decision == 0 or
           self.stimulus_mean == 0):
            string += 'XXXXXXXXXXXXXXXXXXXXXX\n'
            string += 'the duration of all periods must be larger than 0\n'
            string += 'XXXXXXXXXXXXXXXXXXXXXX\n'
        string += 'XXXXXXXXXXXXXXXXXXXXXX\n'
        string += 'Random Dots Motion Task\n'
        string += 'Mean Fixation: ' + str(self.fixation) + '\n'
        string += 'Min Stimulus Duration: ' + str(self.stimulus_min) + '\n'
        string += 'Mean Stimulus Duration: ' + str(self.stimulus_mean) + '\n'
        string += 'Max Stimulus Duration: ' + str(self.stimulus_max) + '\n'
        string += 'Decision: ' + str(self.decision) + '\n'
        string += '(time step: ' + str(self.dt) + '\n'
        string += 'XXXXXXXXXXXXXXXXXXXXXX\n'
        return string

    def new_trial(self, **kwargs):
        """
        new_trial() is called when a trial ends to generate the next trial.
        The following variables are created:
            durations, which stores the duration of the different periods (in
            the case of rdm: fixation, stimulus and decision periods)
            ground truth: correct response for the trial
            coh: stimulus coherence (evidence) for the trial
            obs: observation
        """
        # ---------------------------------------------------------------------
        # Epochs
        # ---------------------------------------------------------------------
        if 'durs' in kwargs.keys():
            fixation = kwargs['durs'][0]
            stimulus = kwargs['durs'][1]
            decision = kwargs['durs'][2]
        else:
            stimulus = tasktools.trunc_exp(self.rng, self.dt,
                                           self.stimulus_mean,
                                           xmin=self.stimulus_min,
                                           xmax=self.stimulus_max)
            # fixation = self.rng.uniform(self.fixation_min, self.fixation_max)
            fixation = self.fixation
            decision = self.decision

        # maximum length of current trial
        self.tmax = fixation + stimulus + decision
        self.fixation_0 = 0
        self.fixation_1 = fixation
        self.stimulus_0 = fixation
        self.stimulus_1 = fixation + stimulus
        self.decision_0 = fixation + stimulus
        self.decision_1 = fixation + stimulus + decision
        # ---------------------------------------------------------------------
        # Trial
        # ---------------------------------------------------------------------
        if 'gt' in kwargs.keys():
            ground_truth = kwargs['gt']
        else:
            ground_truth = self.rng.choice(self.choices)
        if 'coh' in kwargs.keys():
            coh = kwargs['coh']
        else:
            coh = self.rng.choice(self.cohs)

        self.ground_truth = ground_truth
        self.coh = coh
        t = np.arange(0, self.tmax, self.dt)
        obs = np.zeros((len(t), self.n+1))

        fixation_period = np.logical_and(t >= self.fixation_0,
                                         t < self.fixation_1)
        stimulus_period = np.logical_and(t >= self.stimulus_0,
                                         t < self.stimulus_1)
        obs[fixation_period, 0] = 1
        n_stim = int(stimulus/self.dt)
        obs[stimulus_period, 0] = 1
        obs[stimulus_period, 1:] = (1 - coh/100)/2
        obs[stimulus_period, ground_truth] = (1 + coh/100)/2
        obs[stimulus_period, 1:] +=\
            np.random.randn(n_stim, self.n) * self.sigma_dt
        self.obs = obs
        self.t = 0
        self.num_tr += 1

    def _step(self, action, **kwargs):
        """
        _step receives an action and returns:
            a new observation, obs
            reward associated with the action, reward
            a boolean variable indicating whether the experiment has end, done
            a dictionary with extra information:
                ground truth correct response, info['gt']
                boolean indicating the end of the trial, info['new_trial']
        """
        if self.num_tr == 0:
            # start first trial
            self.new_trial()
        # ---------------------------------------------------------------------
        # Reward and observations
        # ---------------------------------------------------------------------
        new_trial = False
        # rewards
        reward = 0
        # observations
        gt = np.zeros((self.n+1,))
        if self.fixation_0 <= self.t < self.fixation_1:
            gt[0] = 1
            if action != 0:
                new_trial = self.abort
                reward = self.R_ABORTED
        elif self.decision_0 <= self.t < self.decision_1:
            gt[self.ground_truth] = 1
            if self.ground_truth == action:
                reward = self.R_CORRECT
            elif self.ground_truth != 0:  # 3-action is the other act
                reward = self.R_FAIL
            new_trial = action != 0
        else:
            gt[0] = 1
        obs = self.obs[int(self.t/self.dt), :]

        # ---------------------------------------------------------------------
        # new trial?
        reward, new_trial = tasktools.new_trial(self.t, self.tmax,
                                                self.dt, new_trial,
                                                self.R_MISS, reward)
        self.t += self.dt

        done = self.num_tr > self.num_tr_exp

        return obs, reward, done, {'new_trial': new_trial, 'gt': gt}

    def step(self, action):
        """
        step receives an action and returns:
            a new observation, obs
            reward associated with the action, reward
            a boolean variable indicating whether the experiment has end, done
            a dictionary with extra information:
                ground truth correct response, info['gt']
                boolean indicating the end of the trial, info['new_trial']
        Note that the main computations are done by the function _step(action),
        and the extra lines are basically checking whether to call the
        new_trial() function in order to start a new trial
        """
        obs, reward, done, info = self._step(action)
        if info['new_trial']:
            self.new_trial()
        return obs, reward, done, info


if __name__ == '__main__':
    env = nalt_RDM(timing=[100, 200, 200, 200, 100])
    observations = []
    rewards = []
    actions = []
    actions_end_of_trial = []
    gt = []
    config_mat = []
    num_steps_env = 100
    for stp in range(int(num_steps_env)):
        action = 1  # env.action_space.sample()
        obs, rew, done, info = env.step(action)
        if done:
            env.reset()
        observations.append(obs)
        if info['new_trial']:
            actions_end_of_trial.append(action)
        else:
            actions_end_of_trial.append(-1)
        rewards.append(rew)
        actions.append(action)
        gt.append(info['gt'])
        if 'config' in info.keys():
            config_mat.append(info['config'])
        else:
            config_mat.append([0, 0])

    rows = 3
    obs = np.array(observations)
    plt.figure()
    plt.subplot(rows, 1, 1)
    plt.imshow(obs.T, aspect='auto')
    plt.title('observations')
    plt.subplot(rows, 1, 2)
    plt.plot(actions, marker='+')
    #    plt.plot(actions_end_of_trial, '--')
    gt = np.array(gt)
    plt.plot(np.argmax(gt, axis=1), 'r')
    #    # aux = np.argmax(obs, axis=1)
    # aux[np.sum(obs, axis=1) == 0] = -1
    # plt.plot(aux, '--k')
    plt.title('actions')
    plt.xlim([-0.5, len(rewards)+0.5])
    plt.subplot(rows, 1, 3)
    plt.plot(rewards, 'r')
    plt.title('reward')
    plt.xlim([-0.5, len(rewards)+0.5])
    plt.show()