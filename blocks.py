def tex_coords(top, bottom, side):
    """ Return a list of the texture squares for the top, bottom and side.

    """
    top = tex_coord(*top)
    bottom = tex_coord(*bottom)
    side = tex_coord(*side)
    result = []
    result.extend(top)
    result.extend(bottom)
    result.extend(side * 4)
    return result

def tex_coord(x, y, n=16):
    """ Return the bounding vertices of the texture square.

    """
    m = 1.0 / n
    dx = x * m
    dy = y * m
    return dx, dy, dx + m, dy, dx + m, dy + m, dx, dy + m


GRASS = tex_coords((1, 0), (0, 1), (0, 0)) #top bottom sides
SAND = tex_coords((1, 1), (1, 1), (1, 1))
BRICK = tex_coords((2, 0), (2, 0), (2, 0))
STONE = tex_coords((2, 1), (2, 1), (2, 1))
END_PORTAL_FRAME = tex_coords((1, 2), (2, 2), (0, 2))
CRAFTING_TABLE = tex_coords((0, 3), (0,3),(1,3))
OBSIDIAN = tex_coords((3, 0), (3,0),(3,0))
DIAMOND_ORE = tex_coords((3, 2), (3,2),(3,2))