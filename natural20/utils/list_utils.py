

def remove_duplicates(list):
    """
    Remove duplicates from a list while preserving ordering
    """
    seen = set()
    unique_list = []
    for item in list:
        if item not in seen:
            seen.add(item)
            unique_list.append(item)

    return unique_list

def bresenham_line_of_sight(x0, y0, x1, y1):
    """Generate coordinates in the line of sight between (x0, y0) and (x1, y1)"""
    points = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy  # error value e_xy

    while True:
        if x0 == x1 and y0 == y1:
            break
        points.append((x0, y0))
        e2 = 2 * err
        if e2 >= dy:  # e_xy+e_x > 0
            err += dy
            x0 += sx
        if e2 <= dx:  # e_xy+e_y < 0
            err += dx
            y0 += sy
    
    return points