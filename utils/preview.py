import numpy as np
from process_layer import process_layer
from utils.xml_loader import load_layers_from_xml
from utils.gcode_handling import initiate_gcode, prepare_next_tool_in_gcode, end_gcode
import config
def generate_preview_from_xml(xml_path, ax):
    ax.clear()

    layers = load_layers_from_xml(xml_path)
    initiate_gcode()
    
    for layer in layers:
        if not layer.enabled:
            continue

        prepare_next_tool_in_gcode(layer.pen_number)
        result = process_layer(layer)
        color = [c / 255 for c in layer.line_color]
        lw = layer.line_width
        h = config.IMAGE_HEIGHT_PXL

        def y_plot(y):
            y = np.array(y)
            return h - y if h is not None else y
        # Contour poligons
        for poly in result.polygons or []:
            polys = [poly] if poly.geom_type == "Polygon" else list(poly.geoms)
            for p in polys:
                x, y = p.exterior.xy
                ax.plot(x, y_plot(y), color=color, linewidth=lw)
                for interior in p.interiors:
                    x, y = interior.xy
                    ax.plot(x, y_plot(y), color=color, linewidth=lw)

        #Skeletons
        print(len(result.skeletons))
        for line in result.skeletons or []:
            #if not line or not isinstance(line[0], (tuple, list)):
            #    continue

            xs = [p[0] for p in line]
            ys = [h - p[1] for p in line]
            ax.plot(xs, ys, color=color, linewidth=lw)

        # Offsets
        for p in result.offsets or []:
            x, y = p.exterior.xy
            ax.plot(x, y_plot(y), color=color, linewidth=lw)
            for interior in p.interiors:
                x, y = interior.xy
                ax.plot(x, y_plot(y), color=color, linewidth=lw)
        # Lawnmover pattern
        for path in result.lawnmower_paths or []:
            xs = [pt[0] for pt in path]
            ys = [y_plot(pt[1]) for pt in path]
            ax.plot(xs, ys, color=color, linewidth=lw)
        # AM pattern
        for ls in result.am_linestrings or []:
            x, y = ls.xy
            ax.plot(x, y_plot(y), color=color, linewidth=lw)

        # Traced SVG lines
        for line in result.svg_lines or []:
            xs = [p[0] for p in line]
            ys = [h - p[1] for p in line]
            ax.plot(xs, ys, color=color, linewidth=lw)

        # Foam Voronoi (CVT) cell edges
        for line in result.foam_edges or []:
            xs = [p[0] for p in line]
            ys = [h - p[1] for p in line]
            ax.plot(xs, ys, color=color, linewidth=lw)

        # Billiard bounce fill trajectories
        for line in result.billiard_paths or []:
            xs = [p[0] for p in line]
            ys = [h - p[1] for p in line]
            ax.plot(xs, ys, color=color, linewidth=lw)

        # Spiral fill strokes
        for line in result.spiral_paths or []:
            xs = [p[0] for p in line]
            ys = [h - p[1] for p in line]
            ax.plot(xs, ys, color=color, linewidth=lw)

        # AM spiral fill
        for ls in result.am_spiral_lines or []:
            x, y = ls.xy
            ax.plot(x, y_plot(y), color=color, linewidth=lw)

        # Dot fill
        for line in result.dot_lines or []:
            xs = [p[0] for p in line]
            ys = [h - p[1] for p in line]
            ax.plot(xs, ys, color=color, linewidth=lw)

        # TSP art
        for line in result.tsp_art_lines or []:
            xs = [p[0] for p in line]
            ys = [h - p[1] for p in line]
            ax.plot(xs, ys, color=color, linewidth=lw)

    end_gcode()
    ax.set_aspect("equal")
    ax.grid(True)