from __future__ import division

import sys
import math
import random
import time

from collections import deque

from pyglet.gl import *
from pyglet.graphics import TextureGroup
from pyglet.window import key, mouse
from pyglet import image
from pyglet import shapes
import threading
from blocks import *
from perlin_noise import PerlinNoise

TICKS_PER_SEC = 60
# originally was 60

FOV = 90.0

max_world_size = 32000
max_build_height = 319

terrain_noise = PerlinNoise(octaves=2)

render = 3

# Size of sectors used to ease block loading.
SECTOR_SIZE = 16

WALKING_SPEED = 5
FLYING_SPEED = 15  

player_pos = (0, 10, 0)

INVENTORY_POS = (195, 100)

GRAVITY = 20.0
MAX_JUMP_HEIGHT = 1.2 # About the height of a block.
# To derive the formula for calculating jump speed, first solve
#    v_t = v_0 + a * t
# for the time at which you achieve maximum height, where a is the acceleration
# due to gravity and v_t = 0. This gives:
#    t = - v_0 / a
# Use t and the desired MAX_JUMP_HEIGHT to solve for v_0 (jump speed) in
#    s = s_0 + v_0 * t + (a * t^2) / 2
JUMP_SPEED = math.sqrt(2 * GRAVITY * MAX_JUMP_HEIGHT)
TERMINAL_VELOCITY = 50

PLAYER_HEIGHT = 2

if sys.version_info[0] >= 3:
    xrange = range

def cube_vertices(x, y, z, n):
    """ Return the vertices of the cube at position x, y, z with size 2*n.

    """
    return [
        x-n,y+n,z-n, x-n,y+n,z+n, x+n,y+n,z+n, x+n,y+n,z-n,  # top
        x-n,y-n,z-n, x+n,y-n,z-n, x+n,y-n,z+n, x-n,y-n,z+n,  # bottom
        x-n,y-n,z-n, x-n,y-n,z+n, x-n,y+n,z+n, x-n,y+n,z-n,  # left
        x+n,y-n,z+n, x+n,y-n,z-n, x+n,y+n,z-n, x+n,y+n,z+n,  # right
        x-n,y-n,z+n, x+n,y-n,z+n, x+n,y+n,z+n, x-n,y+n,z+n,  # front
        x+n,y-n,z-n, x-n,y-n,z-n, x-n,y+n,z-n, x+n,y+n,z-n,  # back
    ]

def slab_vertices(x, y, z, n):
    """ Return the vertices of the cube at position x, y, z with size 2*n.

    """
    return [
        x-n,n,z-n, x-n,n,z+n, x+n,n,z+n, x+n,n,z-n,  # top
        x-n,y-n,z-n, x+n,y-n,z-n, x+n,y-n,z+n, x-n,y-n,z+n,  # bottom
        x-n,y-n,z-n, x-n,y-n,z+n, x-n,n,z+n, x-n,n,z-n,  # left
        x+n,y-n,z+n, x+n,y-n,z-n, x+n,n,z-n, x+n,n,z+n,  # right
        x-n,y-n,z+n, x+n,y-n,z+n, x+n,n,z+n, x-n,n,z+n,  # front
        x+n,y-n,z-n, x-n,y-n,z-n, x-n,n,z-n, x+n,n,z-n,  # back
    ]

gui_blocks = [CRAFTING_TABLE]

TEXTURE_PATH = 'texture_size_test.png'

hotbar_image = image.load('hotbar.png')
player_inventory = image.load('player_inventory.png')
heart = image.load('heart.png')
empty_heart = image.load('heart_empty.png')


FACES = [
    ( 0, 1, 0),
    ( 0,-1, 0),
    (-1, 0, 0),
    ( 1, 0, 0),
    ( 0, 0, 1),
    ( 0, 0,-1),
]


def normalize(position):
    """ Accepts `position` of arbitrary precision and returns the block
    containing that position.

    Parameters
    ----------
    position : tuple of len 3

    Returns
    -------
    block_position : tuple of ints of len 3

    """
    x, y, z = position
    x, y, z = (int(round(x)), int(round(y)), int(round(z)))
    return (x, y, z)


def sectorize(position):
    """ Returns a tuple representing the sector for the given `position`.

    Parameters
    ----------
    position : tuple of len 3

    Returns
    -------
    sector : tuple of len 3

    """
    x, y, z = normalize(position)
    x, y, z = x // SECTOR_SIZE, y // SECTOR_SIZE, z // SECTOR_SIZE
    return (x, 0, z)


class Model(object):

    def __init__(self):

        # A Batch is a collection of vertex lists for batched rendering.
        self.batch = pyglet.graphics.Batch()

        # A TextureGroup manages an OpenGL texture.
        self.group = TextureGroup(image.load(TEXTURE_PATH).get_texture())

        self.chunk_cooldown = 75

        self.current_chunk = (0, 0)
        self.last_chunk = (0, 0)

        # A mapping from position to the texture of the block at that position.
        # This defines all the blocks that are currently in the world.
        self.world = {}

        # Same mapping as `world` but only contains blocks that are shown.
        self.shown = {}

        self.loaded_chunks = []

        # Mapping from position to a pyglet `VertextList` for all shown blocks.
        self._shown = {}

        # Mapping from sector to a list of positions inside that sector.
        self.sectors = {}

        # Simple function queue implementation. The queue is populated with
        # _show_block() and _hide_block() calls
        self.queue = deque()

        self._initialize()
    
    def load_chunk(self, pos=(1, 0)):
        global SECTOR_SIZE, terrain_noise, max_world_size
        if not pos in self.loaded_chunks:
            for x in range(SECTOR_SIZE):
                for z in range(SECTOR_SIZE):
                    height = terrain_noise([x+(pos[0]*SECTOR_SIZE) * max_world_size, z+(pos[1]*SECTOR_SIZE) * max_world_size])
                    # height = height*max_build_height
                    if height > max_build_height:
                        height = max_build_height
                    elif height < 1:
                        height = 1
                    for y in range(int(height)):
                        self.add_block((x+(pos[0]*SECTOR_SIZE), y, z+(pos[1]*SECTOR_SIZE)), GRASS, immediate=False)
                        self.show_block((x+(pos[0]*SECTOR_SIZE), y, z+(pos[1]*SECTOR_SIZE)))
                        
                

            self.loaded_chunks.append((pos[0], pos[1]))

    def unload_chunk(self, pos=(1, 0)):
        global SECTOR_SIZE
        for x in range(SECTOR_SIZE):
            for z in range(SECTOR_SIZE):
                for y in range(10):
                    if (x+(pos[0]*SECTOR_SIZE), y, z+(pos[1]*SECTOR_SIZE)) in self.world:
                        self.remove_block((x+(pos[0]*SECTOR_SIZE), y, z+(pos[1]*SECTOR_SIZE)), immediate=True)
        self.loaded_chunks.remove((pos[0], pos[1]))
    
    def check_chunks(self, x=0, z=0):
        global SECTOR_SIZE
        
        for i in self.loaded_chunks:
            distance = math.dist((i[0], i[1]), (x // SECTOR_SIZE, z // SECTOR_SIZE))
            if distance > render:
                self.unload_chunk((i[0], i[1]))
            
        for x in range(-render, render):
            for z in range(-render, render):
                if not (x+player_pos[0] // SECTOR_SIZE, z+player_pos[2] // SECTOR_SIZE) in self.loaded_chunks:
                    self.load_chunk((x+player_pos[0] // SECTOR_SIZE, z+player_pos[2] // SECTOR_SIZE))

    def moved_chunks(self, chunk1=(0, 0), chunk2=(0, 0)):
        return chunk1 != chunk2

    def get_chunked_coords(self, pos=(0, 0)):
        global SECTOR_SIZE
        return (pos[0] // SECTOR_SIZE, pos[1] // SECTOR_SIZE)


        

    def _initialize(self):
        global render

        '''
        self.chunk_updater = threading.Thread(target=self.check_chunks, args=(player_pos[0], player_pos[2]))
        self.chunk_updater.start()
        '''

        

        """ Initialize the world by placing all the blocks.

        """
        '''
        n = 80  # 1/2 width and height of world
        s = 1  # step size
        y = 0  # initial y height
        for x in xrange(-n, n + 1, s):
            for z in xrange(-n, n + 1, s):
                # create a layer stone an grass everywhere.
                self.add_block((x, y - 2, z), GRASS, immediate=False)
                self.add_block((x, y - 3, z), STONE, immediate=False)
                if x in (-n, n) or z in (-n, n):
                    # create outer walls.
                    pass

        # generate the hills randomly
        o = n - 10
        for _ in xrange(120):
            a = random.randint(-o, o)  # x position of the hill
            b = random.randint(-o, o)  # z position of the hill
            c = -1  # base of the hill
            h = random.randint(1, 6)  # height of the hill
            s = random.randint(4, 8)  # 2 * s is the side length of the hill
            d = 2  # how quickly to taper off the hills
            t = GRASS
            for y in xrange(c, c + h):
                for x in xrange(a - s, a + s + 1):
                    for z in xrange(b - s, b + s + 1):
                        if (x - a) ** 2 + (z - b) ** 2 > (s + 1) ** 2:
                            continue
                        if (x - 0) ** 2 + (z - 0) ** 2 < 5 ** 2:
                            continue
                        self.add_block((x, y, z), t, immediate=False)
                s -= d  # decrement side length so hills taper off
        '''
        '''
        for x in range(-render, render):
            for z in range(-render, render):
                self.load_chunk((x, z))
                # self.unload_chunk((x, z))
        '''
        self.check_chunks(player_pos[0], player_pos[2])


    
        

    def hit_test(self, position, vector, max_distance=8):
        """ Line of sight search from current position. If a block is
        intersected it is returned, along with the block previously in the line
        of sight. If no block is found, return None, None.

        Parameters
        ----------
        position : tuple of len 3
            The (x, y, z) position to check visibility from.
        vector : tuple of len 3
            The line of sight vector.
        max_distance : int
            How many blocks away to search for a hit.

        """
        m = 8
        x, y, z = position
        dx, dy, dz = vector
        previous = None
        for _ in xrange(max_distance * m):
            key = normalize((x, y, z))
            if key != previous and key in self.world:
                return key, previous
            previous = key
            x, y, z = x + dx / m, y + dy / m, z + dz / m
        return None, None

    def exposed(self, position):
        """ Returns False is given `position` is surrounded on all 6 sides by
        blocks, True otherwise.

        """
        x, y, z = position
        for dx, dy, dz in FACES:
            if (x + dx, y + dy, z + dz) not in self.world:
                return True
        return False

    def add_block(self, position, texture, immediate=True):
        """ Add a block with the given `texture` and `position` to the world.

        Parameters
        ----------
        position : tuple of len 3
            The (x, y, z) position of the block to add.
        texture : list of len 3
            The coordinates of the texture squares. Use `tex_coords()` to
            generate.
        immediate : bool
            Whether or not to draw the block immediately.

        """
        if position in self.world:
            self.remove_block(position, immediate)
        self.world[position] = texture
        self.sectors.setdefault(sectorize(position), []).append(position)
        if immediate:
            if self.exposed(position):
                self.show_block(position)
            self.check_neighbors(position)

    def remove_block(self, position, immediate=True):
        """ Remove the block at the given `position`.

        Parameters
        ----------
        position : tuple of len 3
            The (x, y, z) position of the block to remove.
        immediate : bool
            Whether or not to immediately remove block from canvas.

        """
        del self.world[position]
        self.sectors[sectorize(position)].remove(position)
        if immediate:
            if position in self.shown:
                self.hide_block(position)
            self.check_neighbors(position)

    def check_neighbors(self, position):
        """ Check all blocks surrounding `position` and ensure their visual
        state is current. This means hiding blocks that are not exposed and
        ensuring that all exposed blocks are shown. Usually used after a block
        is added or removed.

        """
        x, y, z = position
        for dx, dy, dz in FACES:
            key = (x + dx, y + dy, z + dz)
            if key not in self.world:
                continue
            if self.exposed(key):
                if key not in self.shown:
                    self.show_block(key)
            else:
                if key in self.shown:
                    self.hide_block(key)

    def show_block(self, position, immediate=True):
        """ Show the block at the given `position`. This method assumes the
        block has already been added with add_block()

        Parameters
        ----------
        position : tuple of len 3
            The (x, y, z) position of the block to show.
        immediate : bool
            Whether or not to show the block immediately.

        """
        texture = self.world[position]
        self.shown[position] = texture
        if immediate:
            self._show_block(position, texture)
        else:
            self._enqueue(self._show_block, position, texture)

    def _show_block(self, position, texture):
        """ Private implementation of the `show_block()` method.

        Parameters
        ----------
        position : tuple of len 3
            The (x, y, z) position of the block to show.
        texture : list of len 3
            The coordinates of the texture squares. Use `tex_coords()` to
            generate.

        """
        x, y, z = position
        vertex_data = cube_vertices(x, y, z, 0.5)
        texture_data = list(texture)
        # create vertex list
        # FIXME Maybe `add_indexed()` should be used instead
        self._shown[position] = self.batch.add(24, GL_QUADS, self.group,
            ('v3f/static', vertex_data),
            ('t2f/static', texture_data))

    def hide_block(self, position, immediate=True):
        """ Hide the block at the given `position`. Hiding does not remove the
        block from the world.

        Parameters
        ----------
        position : tuple of len 3
            The (x, y, z) position of the block to hide.
        immediate : bool
            Whether or not to immediately remove the block from the canvas.

        """
        self.shown.pop(position)
        if immediate:
            self._hide_block(position)
        else:
            self._enqueue(self._hide_block, position)

    def _hide_block(self, position):
        """ Private implementation of the 'hide_block()` method.

        """
        try:
            self._shown.pop(position).delete()
        except:
            pass

    def show_sector(self, sector):
        """ Ensure all blocks in the given sector that should be shown are
        drawn to the canvas.

        """
        for position in self.sectors.get(sector, []):
            if position not in self.shown and self.exposed(position):
                self.show_block(position, False)
            else:
                self.add_block(position, GRASS)

    def hide_sector(self, sector):
        """ Ensure all blocks in the given sector that should be hidden are
        removed from the canvas.

        """
        for position in self.sectors.get(sector, []):
            if position in self.shown:
                self.hide_block(position, False)

    def change_sectors(self, before, after):
        """ Move from sector `before` to sector `after`. A sector is a
        contiguous x, y sub-region of world. Sectors are used to speed up
        world rendering.

        """
        before_set = set()
        after_set = set()
        pad = 4
        for dx in xrange(-pad, pad + 1):
            for dy in [0]:  # xrange(-pad, pad + 1):
                for dz in xrange(-pad, pad + 1):
                    if dx ** 2 + dy ** 2 + dz ** 2 > (pad + 1) ** 2:
                        continue
                    if before:
                        x, y, z = before
                        before_set.add((x + dx, y + dy, z + dz))
                    if after:
                        x, y, z = after
                        after_set.add((x + dx, y + dy, z + dz))
        show = after_set - before_set
        hide = before_set - after_set
        for sector in show:
            self.show_sector(sector)
        for sector in hide:
            self.hide_sector(sector)

    def _enqueue(self, func, *args):
        """ Add `func` to the internal queue.

        """
        self.queue.append((func, args))

    def _dequeue(self):
        """ Pop the top function from the internal queue and call it.

        """
        func, args = self.queue.popleft()
        func(*args)

    def process_queue(self):
        """ Process the entire queue while taking periodic breaks. This allows
        the game loop to run smoothly. The queue contains calls to
        _show_block() and _hide_block() so this method should be called if
        add_block() or remove_block() was called with immediate=False

        """
        start = time.perf_counter()
        while self.queue and time.perf_counter() - start < 1.0 / TICKS_PER_SEC:
            self._dequeue()

    def process_entire_queue(self):
        """ Process the entire queue with no breaks.

        """
        while self.queue:
            self._dequeue()

    
        

class Slot():
    def __inti__(self, x=0, y=0, contents=None):
        self.x = x
        self.y = y
        self.contents =contents
    def get_pos(self):
        return (self.x, self.y)
    def get_contents(self):
        return self.contents

class Window(pyglet.window.Window):

    def __init__(self, *args, **kwargs):
        super(Window, self).__init__(*args, **kwargs)

        # Whether or not the window exclusively captures the mouse.
        self.exclusive = False
        self.health = 10
        self.health_cooldown = 500
        self.health_regen = 3010
        self.hurt_batch = pyglet.graphics.Batch()

        self.last_pos = (0, 0, 0)
        
        self.last_chunk = (0, 0)
        self.current_chunk = (0, 0)
        self.gen_chunks = True
        # When flying gravity has no effect and speed is increased.
        self.flying = True

        self.chat_open = False

        # Strafing is moving lateral to the direction you are facing,
        # e.g. moving to the left or right while continuing to face forward.
        #
        # First element is -1 when moving forward, 1 when moving back, and 0
        # otherwise. The second element is -1 when moving left, 1 when moving
        # right, and 0 otherwise.
        self.strafe = [0, 0]

        # Current (x, y, z) position in the world, specified with floats. Note
        # that, perhaps unlike in math class, the y-axis is the vertical axis.
        self.position = (0, 10, 0)

        self.jumping = False

        self.inventory_open = False

        self.gamemode = 'survival'
        # First element is rotation of the player in the x-z plane (ground
        # plane) measured from the z-axis down. The second is the rotation
        # angle from the ground plane up. Rotation is in degrees.
        #
        # The vertical plane rotation ranges from -90 (looking straight down) to
        # 90 (looking straight up). The horizontal rotation range is unbounded.
        self.rotation = (0, 0)

        # Which sector the player is currently in.
        self.sector = None

        # The crosshairs at the center of the screen.
        self.reticle = None

        # Velocity in the y (upward) direction.
        self.dy = 2

        # A list of blocks the player can place. Hit num keys to cycle.
        self.hot_bar = [BRICK, GRASS, SAND, END_PORTAL_FRAME,OBSIDIAN, CRAFTING_TABLE, DIAMOND_ORE]

        # The current block the user can place. Hit num keys to cycle.
        self.block = self.hot_bar[0]

        # Convenience list of num keys.
        self.num_keys = [
            key._1, key._2, key._3, key._4, key._5,
            key._6, key._7, key._8, key._9, key._0]

        # Instance of the model that handles the world.
        self.model = Model()

        

        # The label that is displayed in the top left of the canvas.
        self.label = pyglet.text.Label('', font_name='Arial', font_size=18,
            x=10, y=self.height - 10, anchor_x='left', anchor_y='top',
            color=(0, 0, 0, 255))

        # This call schedules the `update()` method to be called
        # TICKS_PER_SEC. This is the main game event loop.
        pyglet.clock.schedule_interval(self.update, 1.0 / TICKS_PER_SEC)

    def set_exclusive_mouse(self, exclusive):
        """ If `exclusive` is True, the game will capture the mouse, if False
        the game will ignore the mouse.

        """
        super(Window, self).set_exclusive_mouse(exclusive)
        self.exclusive = exclusive

    def get_sight_vector(self):
        """ Returns the current line of sight vector indicating the direction
        the player is looking.

        """
        x, y = self.rotation
        # y ranges from -90 to 90, or -pi/2 to pi/2, so m ranges from 0 to 1 and
        # is 1 when looking ahead parallel to the ground and 0 when looking
        # straight up or down.
        m = math.cos(math.radians(y))
        # dy ranges from -1 to 1 and is -1 when looking straight down and 1 when
        # looking straight up.
        dy = math.sin(math.radians(y))
        dx = math.cos(math.radians(x - 90)) * m
        dz = math.sin(math.radians(x - 90)) * m
        return (dx, dy, dz)

    def get_motion_vector(self):
        """ Returns the current motion vector indicating the velocity of the
        player.

        Returns
        -------
        vector : tuple of len 3
            Tuple containing the velocity in x, y, and z respectively.

        """
        if any(self.strafe):
            x, y = self.rotation
            strafe = math.degrees(math.atan2(*self.strafe))
            y_angle = math.radians(y)
            x_angle = math.radians(x + strafe)
            if self.flying:
                m = math.cos(y_angle)
                dy = math.sin(y_angle)
                if self.strafe[1]:
                    # Moving left or right.
                    dy = 0.0
                    m = 1
                if self.strafe[0] > 0:
                    # Moving backwards.
                    dy *= -1
                # When you are flying up or down, you have less left and right
                # motion.
                dx = math.cos(x_angle) * m
                dz = math.sin(x_angle) * m
            else:
                dy = 0.0
                dx = math.cos(x_angle)
                dz = math.sin(x_angle)
        else:
            dy = 0.0
            dx = 0.0
            dz = 0.0
        return (dx, dy, dz)

    def update(self, dt):
        global player_pos
        """ This method is scheduled to be called repeatedly by the pyglet
        clock.

        Parameters
        ----------
        dt : float
            The change in time since the last call.

        """
        
        self.model.process_queue()
        sector = sectorize(self.position)
        if sector != self.sector:
            self.model.change_sectors(self.sector, sector)
            if self.sector is None:
                self.model.process_entire_queue()
            self.sector = sector
        m = 8
        dt = min(dt, 0.2)
        for _ in xrange(m):
            self._update(dt / m)

        player_pos = self.position
        
    def difference(self, a, b):
        if a > b:
            return a - b
        else:
            return b - a

    def _update(self, dt):
        global PLAYER_HEIGHT, health
        """ Private implementation of the `update()` method. This is where most
        of the motion logic lives, along with gravity and collision detection.

        Parameters
        ----------
        dt : float
            The change in time since the last call.

        """
        # walking
        speed = FLYING_SPEED if self.flying else WALKING_SPEED
        d = dt * speed # distance covered this tick.
        dx, dy, dz = self.get_motion_vector()
        if self.jumping:
            if self.dy == 0:
                self.dy = JUMP_SPEED
        # New position in space, before accounting for gravity.
        dx, dy, dz = dx * d, dy * d, dz * d
        # gravity
        if not self.flying:
            # Update your vertical speed: if you are falling, speed up until you
            # hit terminal velocity; if you are jumping, slow down until you
            # start falling.
            self.dy -= dt * GRAVITY
            self.dy = max(self.dy, -TERMINAL_VELOCITY)
            dy += self.dy * dt
        # collisions
        x, y, z = self.position
        x, y, z = self.collide((x + dx, y + dy, z + dz), PLAYER_HEIGHT)
        
        self.position = (x, y, z)
        if self.flying:
            PLAYER_HEIGHT = 1
        elif not self.flying:
            PLAYER_HEIGHT = 2
        if self.gamemode != 'creative':
            if self.position[1] < -10:
                if self.health_cooldown < 1:
                    self.health -= 2
                    self.health_cooldown = 500
                    self.health_regen = 3010

        if self.health < 1:
            print('You died')
            exit()

        self.health_cooldown -= 1

        if self.health_regen < 1:
            if self.health < 10:
                self.health += 1
                self.health_regen = 3010
        else:
            self.health_regen -= 1
        if self.gen_chunks:
            if self.difference(self.position[0], self.last_pos[0]) < 5  and self.difference(self.position[2], self.last_pos[2]) < 5:
                pass
            else:
                self.last_pos = (self.position[0], self.position[1], self.position[2])
                self.model.check_chunks(player_pos[0], player_pos[2])

    def collide(self, position, height):
        """ Checks to see if the player at the given `position` and `height`
        is colliding with any blocks in the world.

        Parameters
        ----------
        position : tuple of len 3
            The (x, y, z) position to check for collisions at.
        height : int or float
            The height of the player.

        Returns
        -------
        position : tuple of len 3
            The new position of the player taking into account collisions.

        """
        # How much overlap with a dimension of a surrounding block you need to
        # have to count as a collision. If 0, touching terrain at all counts as
        # a collision. If .49, you sink into the ground, as if walking through
        # tall grass. If >= .5, you'll fall through the ground.
        pad = 0.25
        p = list(position)
        np = normalize(position)
        for face in FACES:  # check all surrounding blocks
            for i in xrange(3):  # check each dimension independently
                if not face[i]:
                    continue
                # How much overlap you have with this dimension.
                d = (p[i] - np[i]) * face[i]
                if d < pad:
                    continue
                for dy in xrange(height):  # check each height
                    op = list(np)
                    op[1] -= dy
                    op[i] += face[i]
                    if tuple(op) not in self.model.world:
                        continue
                    p[i] -= (d - pad) * face[i]
                    if face == (0, -1, 0) or face == (0, 1, 0):
                        # You are colliding with the ground or ceiling, so stop
                        # falling / rising.
                        self.dy = 0
                        if face == (0, 1, 0):
                            self.dy = -0.1
                    break
        return tuple(p)

    def on_mouse_press(self, x, y, button, modifiers):
        global gui_blocks
        """ Called when a mouse button is pressed. See pyglet docs for button
        amd modifier mappings.

        Parameters
        ----------
        x, y : int
            The coordinates of the mouse click. Always center of the screen if
            the mouse is captured.
        button : int
            Number representing mouse button that was clicked. 1 = left button,
            4 = right button.
        modifiers : int
            Number representing any modifying keys that were pressed when the
            mouse button was clicked.

        """
        if self.exclusive:
            if not self.inventory_open:
                vector = self.get_sight_vector()
                block, previous = self.model.hit_test(self.position, vector)
                if (button == mouse.RIGHT):
                    if previous:
                        if self.model.world[block] != CRAFTING_TABLE:
                            if block != (round(self.position[0]), round(self.position[1]), round(self.position[2])) or block != (round(self.position[0]), round(self.position[1] + 1), round(self.position[2])):
                                self.model.add_block(previous, self.block)
                        
                elif button == pyglet.window.mouse.LEFT and block:
                    texture = self.model.world[block]
                    if texture != STONE:
                        self.model.remove_block(block)
        else:
            if not self.inventory_open:
                self.set_exclusive_mouse(True)
            else:
                # print(str(self.get_slot(x, y)))
                pass
    
    def get_slot(self, x, y, gui='inventory'):
        global INVENTORY_POS
        if x < INVENTORY_POS[0]:
            return None
        if y < INVENTORY_POS[1]:
            return None
        if x > INVENTORY_POS[0] + player_inventory.width:
            return None
        if y > INVENTORY_POS[1] + player_inventory.height:
            return None

    def on_mouse_motion(self, x, y, dx, dy):
        """ Called when the player moves the mouse.

        Parameters
        ----------
        x, y : int
            The coordinates of the mouse click. Always center of the screen if
            the mouse is captured.
        dx, dy : float
            The movement of the mouse.

        """
        if not self.inventory_open:
            if self.exclusive:
                m = 0.15
                x, y = self.rotation
                x, y = x + dx * m, y + dy * m
                y = max(-90, min(90, y))
                self.rotation = (x, y)

    def on_key_press(self, symbol, modifiers):
        """ Called when the player presses a key. See pyglet docs for key
        mappings.

        Parameters
        ----------
        symbol : int
            Number representing the key that was pressed.
        modifiers : int
            Number representing any modifying keys that were pressed.

        """

        if self.chat_open:
            if symbol != key.ENTER or key.ESCAPE:
                print(str(key[symbol]))
            else:
                self.chat_open = False

        if not self.inventory_open or not self.chat_open:
            if symbol == key.W:
                self.strafe[0] -= 1
            elif symbol == key.S:
                self.strafe[0] += 1
            elif symbol == key.A:
                self.strafe[1] -= 1
            elif symbol == key.D:
                self.strafe[1] += 1
            elif symbol == key.SPACE:
                self.jumping = True
            elif symbol == key.TAB:
                self.flying = not self.flying
            elif symbol in self.num_keys:
                index = (symbol - self.num_keys[0]) % len(self.hot_bar)
                self.block = self.hot_bar[index]
            elif symbol == key.H:
                if self.gamemode == 'creative':
                    self.gamemode == 'survival'
                elif self.gamemode == 'survival':
                    self.gamemode = 'creative'
            elif symbol == key.Q:
                self.gen_chunks = not self.gen_chunks
            elif symbol == key.T or symbol == key.SLASH:
                self.chat_open = True
        
        if symbol == key.E and not self.chat_open:
            if self.inventory_open:
                self.set_exclusive_mouse(True)
                self.inventory_open = False
            else:
                self.inventory_open = True

        elif symbol == key.ESCAPE:
            if not self.chat_open:
                self.set_exclusive_mouse(False)
            else:
                self.chat_open = False
        
        if self.inventory_open:
            self.strafe[0] = 0
            self.strafe[1] = 0
            self.set_exclusive_mouse(False)
            self.jumping = False

    def on_key_release(self, symbol, modifiers):
        """ Called when the player releases a key. See pyglet docs for key
        mappings.

        Parameters
        ----------
        symbol : int
            Number representing the key that was pressed.
        modifiers : int
            Number representing any modifying keys that were pressed.

        """
        if not self.inventory_open:
            if symbol == key.W:
                self.strafe[0] += 1
            elif symbol == key.S:
                self.strafe[0] -= 1
            elif symbol == key.A:
                self.strafe[1] += 1
            elif symbol == key.D:
                self.strafe[1] -= 1
            elif symbol == key.SPACE:
                self.jumping = False
            elif symbol == key.H:
                self.gamemode = 'survival'

    def on_resize(self, width, height):
        """ Called when the window is resized to a new `width` and `height`.

        """
        # label
        self.label.y = height - 10
        # reticle
        if self.reticle:
            self.reticle.delete()
        x, y = self.width // 2, self.height // 2
        n = 10
        self.reticle = pyglet.graphics.vertex_list(4,
            ('v2i', (x - n, y, x + n, y, x, y - n, x, y + n))
        )

    def set_2d(self):
        """ Configure OpenGL to draw in 2d.

        """
        width, height = self.get_size()
        glDisable(GL_DEPTH_TEST)
        viewport = self.get_viewport_size()
        glViewport(0, 0, max(1, viewport[0]), max(1, viewport[1]))
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, max(1, width), 0, max(1, height), -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

    def set_3d(self):
        global FOV
        """ Configure OpenGL to draw in 3d.

        """
        width, height = self.get_size()
        glEnable(GL_DEPTH_TEST)
        viewport = self.get_viewport_size()
        glViewport(0, 0, max(1, viewport[0]), max(1, viewport[1]))
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(FOV, width / float(height), 0.1, 60.0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        x, y = self.rotation
        glRotatef(x, 0, 1, 0)
        glRotatef(-y, math.cos(math.radians(x)), 0, math.sin(math.radians(x)))
        x, y, z = self.position
        glTranslatef(-x, -y, -z)

    def on_draw(self):
        """ Called by pyglet to draw the canvas.

        """
        global INVENTORY_POS
        
        self.clear()
        self.set_3d()
        glColor3d(1, 1, 1)
        
        self.model.batch.draw()
        
        self.set_2d()
        glEnable(GL_BLEND)
        hotbar_image.blit(self.width // 2 - 230, 0, z=-1)
        if self.inventory_open:
            player_inventory.blit(INVENTORY_POS[0], INVENTORY_POS[1])
        for i in range(10):
            if self.gamemode == 'survival':
                if i < self.health:
                    heart.blit(self.width // 2 - 210 + i*21, 60, z=-1)
                else:
                    empty_heart.blit(self.width // 2 - 210 +i*21, 60, z=-1)
        self.draw_label()
        
        if not self.inventory_open:
            self.draw_reticle()
        self.set_3d()
        if not self.inventory_open:
            self.draw_focused_block()

        if self.chat_open:
            empty_heart.blit(100, 100, z=-1)

    def draw_focused_block(self):
        """ Draw black edges around the block that is currently under the
        crosshairs.

        """
        vector = self.get_sight_vector()
        block = self.model.hit_test(self.position, vector)[0]
        if block:
            x, y, z = block
            vertex_data = cube_vertices(x, y, z, 0.51)
            glColor3d(0, 0, 0)
            glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
            pyglet.graphics.draw(24, GL_QUADS, ('v3f/static', vertex_data))
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)

    def draw_label(self):
        """ Draw the label in the top left of the screen.

        """
        x, y, z = self.position
        self.label.text = '%02d (%.2f, %.2f, %.2f) %d / %d' % (
            pyglet.clock.get_fps(), round(x), round(y), round(z),
            len(self.model._shown), len(self.model.world))
        self.label.draw()

    def draw_reticle(self):
        """ Draw the crosshairs in the center of the screen.

        """
        glColor3d(0, 0, 0)
        self.reticle.draw(GL_LINES)

def setup_fog():
    """ Configure the OpenGL fog properties.

    """
    # Enable fog. Fog "blends a fog color with each rasterized pixel fragment's
    # post-texturing color."
    glEnable(GL_FOG)
    # Set the fog color.
    glFogfv(GL_FOG_COLOR, (GLfloat * 4)(0.5, 0.69, 1.0, 1))
    # Say we have no preference between rendering speed and quality.
    glHint(GL_FOG_HINT, GL_DONT_CARE)
    # Specify the equation used to compute the blending factor.
    glFogi(GL_FOG_MODE, GL_LINEAR)
    # How close and far away fog starts and ends. The closer the start and end,
    # the denser the fog in the fog range.
    glFogf(GL_FOG_START, 40.0)
    glFogf(GL_FOG_END, 60.0)


def setup():
    """ Basic OpenGL configuration.

    """
    # Set the color of "clear", i.e. the sky, in rgba.
    glClearColor(0.5, 0.69, 1.0, 1)
    # Enable culling (not rendering) of back-facing facets -- facets that aren't
    # visible to you.
    glEnable(GL_CULL_FACE)
    # Set the texture minification/magnification function to GL_NEAREST (nearest
    # in Manhattan distance) to the specified texture coordinates. GL_NEAREST
    # "is generally faster than GL_LINEAR, but it can produce textured images
    # with sharper edges because the transition between texture elements is not
    # as smooth."
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
    setup_fog()


def main():
    window = Window(width=800, height=600, caption='Pyglet', resizable=True)
    # Hide the mouse cursor and prevent the mouse from leaving the window.
    window.set_exclusive_mouse(True)
    setup()
    pyglet.app.run()


if __name__ == '__main__':
    main()
