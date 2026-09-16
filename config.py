# Scaling
AUTO_SCALE_FAC = None
PIXEL_PER_MM = None
IMAGE_HEIGHT_PXL = None
CURRENT_PEN_NUMBER = None

# Working driectory
WORKING_DIR = ""

# Mode names
mode_simple_contour = "simple contour"
mode_inward_offset_fill = "inward offset fill"
mode_lawnmover_fill = "lawnmover fill"
mode_skeletonized_lines = "skeletonized lines"
mode_AM_fill_full_canvas = "AM fill full canvas"
mode_AM_fill_inside_contours = "AM fill inside contours"
mode_trace_svg = "trace SVG"
mode_foam_voronoi = "foam voronoi cells"
mode_billiard_fill = "billiard bounce fill"
mode_spiral_fill = "spiral fill"
mode_AM_spiral_fill_full_canvas = "AM spiral fill full canvas"
mode_AM_spiral_fill_inside_contours = "AM spiral fill inside contours"
mode_dot_fill_full_canvas = "dot fill full canvas"
mode_dot_fill_inside_contours = "dot fill inside contours"
mode_tsp_art_full_canvas = "TSP art full canvas"
mode_tsp_art_inside_contours = "TSP art inside contours"


# Feed
FEED = 5000 #8000 mm/min
TRAVEL_FEED = 6000 #10000 mm/min
# Drawing area
DRWAING_AREA_HEIGHT = 76 #mm
DRWAING_AREA_LENGHT = 162 #mm

# Pen drop off positions
PEN_DROP_OFF_Z_HEIGHT = 10 #10
TOOL_APPROACH_FEED = 2000 #mm/min

PEN_DROP_OFF_X = 190 #mm #used to be 187mm
PEN_DROP_OFF_X_APPROACH = 20 #mm

PEN_1_Y = 1 #mm
PEN_2_Y = 13.5 #mm
PEN_3_Y = 26.0 #mm
PEN_4_Y = 38.2 #mm
PEN_5_Y = 50.5 #mm
PEN_6_Y = 62.7 #mm
PEN_7_Y = 74.9 #mm

PEN_1_DROP_COORS = [PEN_DROP_OFF_X, PEN_1_Y-DRWAING_AREA_HEIGHT/2]
PEN_2_DROP_COORS = [PEN_DROP_OFF_X, PEN_2_Y-DRWAING_AREA_HEIGHT/2]
PEN_3_DROP_COORS = [PEN_DROP_OFF_X, PEN_3_Y-DRWAING_AREA_HEIGHT/2]
PEN_4_DROP_COORS = [PEN_DROP_OFF_X, PEN_4_Y-DRWAING_AREA_HEIGHT/2]
PEN_5_DROP_COORS = [PEN_DROP_OFF_X, PEN_5_Y-DRWAING_AREA_HEIGHT/2]
PEN_6_DROP_COORS = [PEN_DROP_OFF_X, PEN_6_Y-DRWAING_AREA_HEIGHT/2]
PEN_7_DROP_COORS = [PEN_DROP_OFF_X, PEN_7_Y-DRWAING_AREA_HEIGHT/2]

PEN_DROP_OFF_COORDINATES = [PEN_1_DROP_COORS, PEN_2_DROP_COORS, PEN_3_DROP_COORS, PEN_4_DROP_COORS, PEN_5_DROP_COORS, PEN_6_DROP_COORS, PEN_7_DROP_COORS]

PEN_PICK_UP_Z_HEIGHT = 0

PEN_PICK_UP_X = 190 #mm #was 189 mm before
PEN_PICK_UP_X_APPROACH = 25 #mm

PEN_1_PICK_COORS = [PEN_PICK_UP_X, PEN_1_Y-DRWAING_AREA_HEIGHT/2]
PEN_2_PICK_COORS = [PEN_PICK_UP_X, PEN_2_Y-DRWAING_AREA_HEIGHT/2]
PEN_3_PICK_COORS = [PEN_PICK_UP_X, PEN_3_Y-DRWAING_AREA_HEIGHT/2]
PEN_4_PICK_COORS = [PEN_PICK_UP_X, PEN_4_Y-DRWAING_AREA_HEIGHT/2]
PEN_5_PICK_COORS = [PEN_PICK_UP_X, PEN_5_Y-DRWAING_AREA_HEIGHT/2]
PEN_6_PICK_COORS = [PEN_PICK_UP_X, PEN_6_Y-DRWAING_AREA_HEIGHT/2]
PEN_7_PICK_COORS = [PEN_PICK_UP_X, PEN_7_Y-DRWAING_AREA_HEIGHT/2]

PEN_PICK_UP_COORDINATES = [PEN_1_PICK_COORS, PEN_2_PICK_COORS, PEN_3_PICK_COORS, PEN_4_PICK_COORS, PEN_5_PICK_COORS, PEN_6_PICK_COORS, PEN_7_PICK_COORS]