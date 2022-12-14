import pybullet as pb
import os
import numpy as np
from poppy_env import PoppyEnv

class PoppyErgoEnv(PoppyEnv):
    
    # Ergo-specific urdf loading logic
    def load_urdf(self, use_fixed_base=False):
        fpath = os.path.dirname(os.path.abspath(__file__))
        pb.setAdditionalSearchPath(fpath)
        robot_id = pb.loadURDF(
            'poppy_ergo.pybullet.urdf',
            basePosition = (0, 0, .43),
            baseOrientation = pb.getQuaternionFromEuler((0,0,0)),
            useFixedBase=use_fixed_base,
        )
        return robot_id

    # Get mirrored version of position across left/right halves of body
    def mirror_position(self, position):
        mirrored = np.empty(len(position))
        for i, name in self.joint_name.items():
            sign = 1 if name[-2:] == "_y" else -1 # don't negate y-axis rotations
            mirror_name = name # swap right and left
            if name[:2] == "l_": mirror_name = "r_" + name[2:]
            if name[:2] == "r_": mirror_name = "l_" + name[2:]
            mirrored[self.joint_index[mirror_name]] = position[i] * sign        
        return mirrored        

    # Get image from head camera
    def get_camera_image(self):

        # Get current pose of head camera
        # link index should be same as parent joint index?
        state = pb.getLinkState(self.robot_id, self.joint_index["head_cam"])
        pos, quat = state[:2]
        M = np.array(pb.getMatrixFromQuaternion(quat)).reshape((3,3)) # local z-axis is third column

        # Calculate camera target and up vector
        camera_position = tuple(p + d for (p,d) in zip(pos, .1*M[:,2]))
        target_position = tuple(p + d for (p,d) in zip(pos, .4*M[:,2]))
        up_vector = tuple(M[:,1])
        
        # Capture image
        width, height = 128, 128
        # width, height = 8, 8 # doesn't actually make much speed difference
        view = pb.computeViewMatrix(
            cameraEyePosition = camera_position,
            cameraTargetPosition = target_position, # focal point
            cameraUpVector = up_vector,
        )
        proj = pb.computeProjectionMatrixFOV(
            # fov = 135,
            fov = 90,
            aspect = height/width,
            nearVal = 0.01,
            # farVal should be large enough to eliminate the unexpected white area(because ur camera is not expected to see that far)
            farVal = 20.0,
        )
        # rgba shape is (height, width, 4)
        _, _, rgba, _, _ = pb.getCameraImage(
            width, height, view, proj,
            flags = pb.ER_NO_SEGMENTATION_MASK) # not much speed difference
        # rgba = np.empty((height, width, 4)) # much fafr than pb.getCameraImage
        return rgba, view, proj
            
# convert from physical robot angles to pybullet angles
# angles[name]: angle for named joint (in degrees)
# degrees are converted to radians
def convert_angles(angles):
    cleaned = {}
    for m,p in angles.items():
        cleaned[m] = p * np.pi / 180
    return cleaned

if __name__ == "__main__":
    
    env = PoppyErgoEnv(pb.POSITION_CONTROL)

    # got from running camera.py
    cam = (1.200002670288086,
        15.999960899353027,
        -31.799997329711914,
        (-0.010284600779414177, -0.012256712652742863, 0.14000000059604645))
    pb.resetDebugVisualizerCamera(*cam)

    input('...')
