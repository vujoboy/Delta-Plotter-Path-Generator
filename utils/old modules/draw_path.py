from shapely.geometry import LineString
import matplotlib.pyplot as plt
import cv2

def draw_am_polylines_on_image(img, polylines, line_color='blue'):
    plt.figure(figsize=(12,6))
    plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    for pl in polylines:
        xs = [p[0] for p in pl]
        ys = [p[1] for p in pl]
        plt.plot(xs, ys, line_color, linewidth=2)
    plt.title("AM-modulated polylines (constant cycles per pixel)")
    plt.show()

def draw_linestrings_on_image(img, linestrings, line_color='blue'):
    # Normalize to list
    if isinstance(linestrings, LineString):
        linestrings = [linestrings]

    plt.figure(figsize=(12,6))
    plt.imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

    for ls in linestrings:
        x, y = ls.xy   # Shapely gives separate arrays
        plt.plot(x, y, line_color, linewidth=2)

    plt.title("AM-modulated LineStrings")
    plt.show()