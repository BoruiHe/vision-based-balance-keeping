import pybullet as pb
from pybullet_data import getDataPath
import time
import numpy as np
import pybullet_data

class PoppyEnv(object):

    # override this for urdf logic, should return robot pybullet id
    def load_urdf(self, use_fixed_base=False):
        return 0

    def __init__(self,
        control_mode=pb.POSITION_CONTROL,
        timestep=1/240,
        control_period=1,
        show=True,
        step_hook=None,
        use_fixed_base=False,
        global_scale=10,
        gravity = True
    ):

        # step_hook(env, action) is called in each env.step(action)
        if step_hook is None: step_hook = lambda env, action: None

        self.control_mode = control_mode
        self.timestep = timestep
        self.control_period = control_period
        self.show = show
        self.step_hook = step_hook

        self.client_id = pb.connect(pb.GUI if show else pb.DIRECT)
        if show: pb.configureDebugVisualizer(pb.COV_ENABLE_SHADOWS, 0)
        pb.setTimeStep(timestep)
        if gravity:
            pb.setGravity(0, 0, -9.8)
        else:
            pb.setGravity(0, 0, 0)
        pb.setAdditionalSearchPath(getDataPath())
        planeId = pb.loadURDF("plane.urdf")

        # 5 cubes around the poppy and table as background
        # Box size is [1,1,1]. z_pos(height) = globalScaling/2
        pb.setAdditionalSearchPath(pybullet_data.getDataPath())
        gs = global_scale
        pos_ls = [[0,gs,gs/2], [0,-gs,gs/2], [gs,0,gs/2], [-gs,0,gs/2], [0,0,3*gs/2]]
        
        texture_ls = ['lake.png', 'monkey.png', 'forest.png', 'city.png', 'sky.png']
        for i in range(5):
            cubeid = pb.loadURDF('cube.urdf', useFixedBase=1, globalScaling= gs)
            _, ori = pb.getBasePositionAndOrientation(cubeid)
            pb.resetBasePositionAndOrientation(cubeid, pos_ls[i], ori)
            pb.changeVisualShape(cubeid, -1, textureUniqueId= pb.loadTexture(texture_ls[i]))
            if i==1:
                quat = pb.getQuaternionFromEuler([0, np.pi, 0])
                pb.resetBasePositionAndOrientation(cubeid, pb.getBasePositionAndOrientation(cubeid)[0], quat)    
            elif i==2:
                quat = pb.getQuaternionFromEuler([np.pi / 2, 0, 0])
                pb.resetBasePositionAndOrientation(cubeid, pb.getBasePositionAndOrientation(cubeid)[0], quat)
            elif i==3:
                quat = pb.getQuaternionFromEuler([np.pi / 2, 0, 0])
                pb.resetBasePositionAndOrientation(cubeid, pb.getBasePositionAndOrientation(cubeid)[0], quat)
        
        # use overridden loading logic
        self.robot_id = self.load_urdf(use_fixed_base)

        self.boundary = {'x': (-gs/2, gs/2), 'y':(-gs/2, gs/2), 'z':(0, pb.getBasePositionAndOrientation(self.robot_id)[0][2])}

        self.num_joints = pb.getNumJoints(self.robot_id)
        self.joint_name, self.joint_index, self.joint_fixed = {}, {}, {}
        for i in range(self.num_joints):
            info = pb.getJointInfo(self.robot_id, i)
            name = info[1].decode('UTF-8')
            self.joint_name[i] = name
            self.joint_index[name] = i
            self.joint_fixed[i] = (info[2] == pb.JOINT_FIXED)
        
        self.initial_state_id = pb.saveState(self.client_id)
    
    def reset(self):
        pb.restoreState(stateId = self.initial_state_id)
    
    def close(self):
        pb.disconnect()
        
    def step(self, action=None, sleep=None):
        
        self.step_hook(self, action)
    
        if action is not None:
            duration = self.control_period * self.timestep
            distance = np.fabs(action - self.get_position())
            pb.setJointMotorControlArray(
                self.robot_id,
                jointIndices = range(len(self.joint_index)),
                controlMode = self.control_mode,
                targetPositions = action,
                targetVelocities = [0]*len(action),
                positionGains = [.25]*len(action), # important for constant position accuracy
                # maxVelocities = distance / duration,
            )

        if sleep is None: sleep = self.show # True
        if sleep:
            for _ in range(self.control_period):
                start = time.perf_counter()
                pb.stepSimulation()
                duration = time.perf_counter() - start
                remainder = self.timestep - duration
                if remainder > 0: time.sleep(remainder)
        else:
            for _ in range(self.control_period):
                pb.stepSimulation()

    # base position/orientation and velocity/angular
    def get_base(self):
        pos, orn = pb.getBasePositionAndOrientation(self.robot_id)
        vel, ang = pb.getBaseVelocity(self.robot_id)
        return pos, orn, vel, ang
    def set_base(self, pos=None, orn=None, vel=None, ang=None):
        _pos, _orn, _vel, _ang = self.get_base()
        if pos == None: pos = _pos
        if orn == None: orn = _orn
        if vel == None: vel = _vel
        if ang == None: ang = _ang
        pb.resetBasePositionAndOrientation(self.robot_id, pos, orn)
        pb.resetBaseVelocity(self.robot_id, vel, ang)
    
    # get/set joint angles as np.array
    def get_position(self):
        states = pb.getJointStates(self.robot_id, range(len(self.joint_index)))
        return np.array([state[0] for state in states])    
    def set_position(self, position):
        for p, angle in enumerate(position):
            pb.resetJointState(self.robot_id, p, angle)

    # convert a pypot style dictionary {... name:angle ...} to joint angle array
    # if convert == True, convert from degrees to radians
    def angle_array(self, angle_dict, convert=True):
        angle_array = np.zeros(self.num_joints)
        for name, angle in angle_dict.items():
            angle_array[self.joint_index[name]] = angle
        if convert: angle_array *= np.pi / 180
        return angle_array
    # convert back from dict to array
    def angle_dict(self, angle_array, convert=True):
        return {
            name: angle_array[j] * 180/np.pi
            for j, name in enumerate(self.joint_index)}

    # pypot-style command, goes to target joint position with given speed
    # target is a joint angle array
    # speed is desired joint speed
    # if hang==True, wait for user enter at each timestep of motion
    def goto_position(self, target, speed=1., hang=False):

        current = self.get_position()
        distance = np.sum((target - current)**2)**.5
        duration = distance / speed

        num_steps = int(duration / (self.timestep * self.control_period) + 1)
        weights = np.linspace(0, 1, num_steps).reshape(-1,1)
        trajectory = weights * target + (1 - weights) * current

        positions = np.empty((num_steps, self.num_joints))
        for a, action in enumerate(trajectory):
            self.step(action)
            positions[a] = self.get_position()
            if hang: input('..')

        return positions