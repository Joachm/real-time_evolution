import nmmo
from nmmo.render.replay_helper import FileReplayHelper
import numpy as np
import random
import copy
import pickle

from real_time_evolution import mutate, pick_best
from agent_neural_net import get_input, PolicyNet, save_state
from logging_functions import calculate_avg_lifetime

replay_helper = FileReplayHelper()
#import torch
#torch.set_num_threads(1)


config = nmmo.config.Default

##TODO copy a folder "modded_NMMO" to this folder!
##this function must be added in the nmmo source, nmmo/entity/entity_manager.py
#def spawn_individual(self,r, c, agent_id):

#  agent_loader = self.config.PLAYER_LOADER(self.config, self._np_random)
#  agent = next(agent_loader)
#  agent = agent(self.config, agent_id)
#  resiliant_flag = False
#  player = Player(self.realm, (r,c), agent, resiliant_flag)
#  super().spawn_entity(player)

# Define the amount of resources on the map
nmmo.config.Default.MAP_CENTER=32
nmmo.config.Default.PROGRESSION_SPAWN_CLUSTERS=4
nmmo.config.Default.PROGRESSION_SPAWN_UNIFORMS=8

# Define the basic things
nmmo.config.Default.TERRAIN_WATER = 0.5
nmmo.config.Default.TERRAIN_DISABLE_STONE = True
nmmo.config.Default.TERRAIN_GRASS = 0.6
nmmo.config.Default.TERRAIN_FOILAGE = 0.5
nmmo.config.Default.TERRAIN_FLIP_SEED = True
nmmo.config.Default.HORIZON = 2**15-1

# Remove the death fog
nmmo.config.Default.PLAYER_DEATH_FOG_FINAL_SIZE = 0
nmmo.config.Default.PLAYER_DEATH_FOG_SPEED = 0


##Disable system modes
nmmo.config.Default.COMBAT_SYSTEM_ENABLED = True
nmmo.config.Default.EXCHANGE_SYSTEM_ENABLED = False
nmmo.config.Default.COMMUNICATION_SYSTEM_ENABLED = False
nmmo.config.Default.PROFESSION_SYSTEM_ENABLED = False
nmmo.config.Default.PROGRESSION_SYSTEM_ENABLED = False
nmmo.config.Default.EQUIPMENT_SYSTEM_ENABLED = False
nmmo.config.Default.NPC_SYSTEM_ENABLED = True
nmmo.config.Default.COMBAT_SPAWN_IMMUNITY = 0
nmmo.config.Default.COMBAT_MELEE_REACH = 1
nmmo.config.Default.COMBAT_RANGE_REACH = 1
nmmo.config.Default.COMBAT_MAGE_REACH = 1

##Population Size
nmmo.config.Default.PLAYER_N = 64
nmmo.config.Default.NPC_N = 0
NPCs = nmmo.config.Default.NPC_N

##Player Input
nmmo.config.Default.PLAYER_N_OBS = 25
nmmo.config.Default.PLAYER_VISION_RADIUS = 7



env = nmmo.Env()
player_N = env.config.PLAYER_N

obs = env.reset()#[0]

env.realm.record_replay(replay_helper)

# Define the model
input_size = 3775
hidden_size1 = 225
hidden_size2 = 75
output_size = 5
output_size_attack = player_N+1+NPCs

# Random weights with a FF network
model_dict = {i+1: PolicyNet(output_size, output_size_attack)  for i in range(player_N)} # Dictionary of random models for each agent


# Forward pass with a feed forward NN
action_list = []
action_list_attack = []

for i in range(env.config.PLAYER_N):
  if (env.realm.players.corporeal[1].alive):
    # Get the observations
    inp = get_input(obs[i+1]['Tile'], obs[i+1]['Entity'],env.realm.players.entities[i+1].pos)
    # Get move actions
    output, output_attack = model_dict[i+1](inp)
    # Get attack actions (target, since agents only do melee combat)
    #output_attack = model_dict[i+1][1](input)
    action_list.append(output.argmax())
    action_list_attack.append(output_attack.argmax())

actions = {}
for i in range(env.config.PLAYER_N):
  actions[i+1] = {"Move":{"Direction":1}, "Attack":{"Style":0,"Target":int(action_list_attack[i])}}

replay_helper.reset()

life_durations = {i+1: 0 for i in range(env.config.PLAYER_N)}

# Getting spawn positions
spawn_positions = []
for i in range(player_N):
  spawn_positions.append(env.realm.players.entities[i+1].spawn_pos)

# Setting up the average lifetime dictionary
avg_lifetime = {}

# Set up a list of all visited tiles by all agents
all_visited = []

# Set up max lifetime
max_lifetime = 0
max_lifetime_dict = {}

steps = 200_000

# The main loop
for step in range(steps):
  #print(step, obs[1]['Entity'][0])
  #print(env.realm.players.entities.keys())
  if step%100==0:
    print(step) 
  # Uncomment for saving replays
  #if i%1000 == 0:
  #  replay_file = f"/content/replay1"
  #  replay_helper.save(replay_file, compress=True)

  current_oldest = life_durations[max(life_durations, key=life_durations.get)]
  if current_oldest > max_lifetime:
    max_lifetime = current_oldest

  # Assign the top-all-time age record to the current tick
  max_lifetime_dict[step] = max_lifetime

  if (step+1)%10000 == 0:
    print('reset env') 
    env.close()
    env = nmmo.Env()
    obs = env.reset()#[0]

  #If the number of agents alive doesn't correspond to PLAYER_N, spawn new offspring
  for i in range(player_N):
    if env.num_agents != player_N: ##TODO: rewrite using dones
      if i+1 not in env.realm.players.entities:
        parent = pick_best(env, player_N, life_durations)
        #env.realm.players.cull()
        try:
        # Spawn individual in the same place as parent
          x, y = env.realm.players.entities[parent].pos
          #x, y = random.choice(spawn_positions)
        except:
        # Spawn individual at a random spawn location
          x, y = random.choice(spawn_positions)

        spawn_positions[i] = (x,y)
        env.realm.players.spawn_individual(x, y, i+1)
        # Upon the "birth" of a new agent, reset the life duration and visited tiles
        life_durations[i+1] = 0

        model_dict[i+1] = copy.deepcopy(model_dict[parent])

        mutate(i+1, parent, model_dict, life_durations, alpha=0.02, dynamic_alpha=True)

    # Check if agents are alive, and if someone dies ignore their action
    if i+1 in env.realm.players.entities and i+1 in obs:
      life_durations[i+1] += 1


      inp = get_input(obs[i+1]['Tile'], obs[i+1]['Entity'], env.realm.players.entities[i+1].pos)
      output, output_attack = model_dict[i+1](inp)

      ### action_list.append(output)
      actions[i+1] = {"Move":{"Direction":int(output)}, "Attack":{"Style":0,"Target":int(output_attack)}, "Use":{"InventoryItem":0}}

    else: actions[i+1] = {}

  # Run a step
  obs, rewards, dones, infos = env.step(actions) ##TODO: why not use DONES to replace?

  if (step+1)%2000==0:
    print('save replay')
    replay_helper.save("replay_testing_"+str(step), compress=False)
    del replay_helper
    replay_helper = FileReplayHelper()
    env.realm.record_replay(replay_helper)
    replay_helper.reset()
  if (step+1)%50_000==0:
    print('save population weights')
    pickle.dump(model_dict,open('agents_model_dict_'+str(step)+'.pickle','wb'))
#!tar chvfz weights_128_02_05_25.tar.gz weights/*



# Save replay file and the weights

#replay_file = f"/content/replay1"
#replay_helper.save("no_brain22", compress=False)
#save_state(model_dict, f"weights")
pickle.dump(model_dict,open('agents_model_dict_final.pickle','wb'))

  # Calculate average lifetime of all agents every 20 steps

  #if (step+1)%20 ==0:
  #avg_lifetime[step] = calculate_avg_lifetime(env, obs, player_N)
  #print('average_lifetime:', avg_lifetime[step])

  ##get agent actions
  #for i in range(env.config.PLAYER_N):



'''
import matplotlib.pyplot as plt

# Extracting keys and values
keys = list(avg_lifetime.keys())
values = list(avg_lifetime.values())

# Plotting
plt.bar(keys, values)
plt.xlabel('Keys')
plt.ylabel('Values')
plt.title('Average lifetime per step')
plt.show()


# This is how to get food level
env.realm.players.entities[1].__dict__['food'].val
env.realm.players.entities[1].__dict__['time_alive'].val

env.realm.players.entities[1].__dict__['status'].__dict__['freeze'].val

env.realm.players.entities[1].State.__dict__
'''