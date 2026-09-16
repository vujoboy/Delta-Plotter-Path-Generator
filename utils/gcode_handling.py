import config

# g-code path
out = open("output.nc", "w")

isPenDown = False
Feed = 5000 #8000
zFeed = 5000 # 5000
travelFeed = 10000 #10000

# g-code procedures
penUp = ";Pen up \nG1 Z2 F8000 \nG4 P0.01" #F5000
penDown = ";Pen down \nG1 Z14 F8000" #F5000

#machine parameters
armL = 100
rodS = 111 #Distance between linear rails (146 mm) minus the distance between the carriage pivot points (35 mm)
shiftX = 102 #102
shiftY = rodS/2

def scale_point(input_point):
    return input_point * config.AUTO_SCALE_FAC

def trX(x, y, arm):
    transformedX = round( -(arm**2 - y**2)**0.5 + x, 3)
    return transformedX

def trY(x, y, arm, rodSpacing): 
    transformedY = round( -(arm**2 - (rodSpacing-y)**2)**0.5 + x, 3)
    return transformedY
    
def getFeed():
    if (isPenDown):
        return config.FEED
    else:
        return config.TRAVEL_FEED

def write_ring(ring):
    global isPenDown
    h = config.IMAGE_HEIGHT_PXL

    for j in range(len(ring)):
        px, py = ring[j]
        
        sx = scale_point(px) + shiftX
        sy = scale_point(h) - scale_point(py) + shiftY - scale_point(h) / 2
        x = trX(sx, sy, armL)
        y = trY(sx, sy, armL, rodS)

        print("G1 X", x, " Y", y, " F", getFeed(), sep='', file=out)

        if j == 0:
            print(penDown, file=out)
            isPenDown = True
                
    # Return to the first point
    
    px, py = ring[0]

    sx = scale_point(px) + shiftX
    sy = scale_point(h) - scale_point(py) + shiftY - scale_point(h) / 2
    x = trX(sx, sy, armL)
    y = trY(sx, sy, armL, rodS)

    print("G1 X", x, " Y", y, " F", getFeed(), sep='', file=out)
    print(penUp, file=out)
    isPenDown = False

def write_poligons_to_gcode(poligons, h):
    #Write poligons to gcode file
    print("write_poligons_to_gcode to be finished") 

    for i in range(len(poligons)):
        print("; - - - contour", i, "start", file=out)

        poly = poligons[i]

        # Write exterior
        ring = list(poly.exterior.coords)
        write_ring(ring)

        # Write interiors
        for interior in poly.interiors:
            ring = list(interior.coords)
            write_ring(ring)          

def initiate_gcode():
    print("G90", file = out)
    print("$H", file = out) #home before start
    print(penUp, file = out) #lift pen in the beginning

def park_current_pen():
    # If there is a pen in the pen holder
    if config.CURRENT_PEN_NUMBER != None:
        # Put down current tool with the following steps
        x, y = config.PEN_DROP_OFF_COORDINATES[config.CURRENT_PEN_NUMBER] # Get coordinates of current pens parking position
        x_approach = x - config.PEN_DROP_OFF_X_APPROACH

        sx = x + shiftX
        sx_approach = x_approach + shiftX
        sy = y + shiftY

        x = trX(sx, sy, armL)
        x_approach = trX(sx_approach, sy, armL)
        y = trY(sx, sy, armL, rodS)
        y_approach = trY(sx_approach,sy,armL,rodS)

        # Move to begining of pen drop off approch path
        print("G1 X", x_approach, " Y", y_approach, " F", getFeed(), sep='', file=out)
        # Move pen holder to correct Z height for approach
        print("G1 Z", config.PEN_DROP_OFF_Z_HEIGHT, " F", zFeed, sep='', file=out)
        # Perform approach and enter pen into magazine
        print("G1 X", x, " Y", y, " F", config.TOOL_APPROACH_FEED, sep='', file=out)
        # Wait a bit for stability
        print("G4 P0.2", file=out)
        # Back off and separate pen holder from pen
        print("G1 X", x_approach, " Y", y_approach, " F", config.TOOL_APPROACH_FEED, sep='', file=out)
        
        print("Pen", config.CURRENT_PEN_NUMBER, "is parked in magazine", sep=' ')
        config.CURRENT_PEN_NUMBER = None

def take_pen(pen_number):
    # If pen there is NO pen in the pen holder
    if config.CURRENT_PEN_NUMBER == None:
        # Pick up pen with the following steps
        x, y = config.PEN_PICK_UP_COORDINATES[pen_number] # Get coordinates of pen to pick up
        x_approach = x - config.PEN_PICK_UP_X_APPROACH
        
        sx = x + shiftX
        sx_approach = x_approach + shiftX
        sy = y + shiftY

        x = trX(sx, sy, armL)
        x_approach = trX(sx_approach, sy, armL)
        y = trY(sx, sy, armL, rodS)
        y_approach = trY(sx_approach,sy,armL,rodS)

        # Move to begining of pen pick up approch path
        print("G1 X", x_approach, " Y", y_approach, " F", getFeed(), sep='', file=out)
        # Move pen holder to correct Z height for approach
        print("G1 Z", config.PEN_PICK_UP_Z_HEIGHT, " F", zFeed, sep='', file=out)
        # Perform approach and pick up pen from magazine
        print("G1 X", x, " Y", y, " F", config.TOOL_APPROACH_FEED, sep='', file=out)
        # Wait a bit for stability
        print("G4 P0.2", file=out)
        # Back off with pen
        print("G1 X", x_approach, " Y", y_approach, " F", config.TOOL_APPROACH_FEED, sep='', file=out)
        
        print("Pen", pen_number, "is taken from magazine", sep=' ')
        config.CURRENT_PEN_NUMBER = pen_number

def prepare_next_tool_in_gcode(to_be_prepared_tool_number):
    if (config.CURRENT_PEN_NUMBER != to_be_prepared_tool_number):
        # Park current pen if a pen is in holder
        park_current_pen()
        # Take selected pen
        take_pen(to_be_prepared_tool_number)

def start_layer_in_gcode():
    print(";xxxxxxxxxxxxxx LAYER START xxxxxxxxxxxxxx", file = out)  

def end_layer_in_gcode():
    print(";xxxxxxxxxxxxxx  LAYER END  xxxxxxxxxxxxxx", file = out)    

def end_gcode():
    print(penUp, file = out) #lift pen at program end
    park_current_pen()
    
    print("G4 P1", file = out) #wait before homeing
    print("$H", file = out) #home at program and
    out.close()
    global isPenDown
    isPenDown = False
    config.CURRENT_PEN_NUMBER = None

def write_linepath_to_gcode(path_coords, h):
    """
    path_coords: list of (x,y) points (open polyline)
    h: image height (used by your existing transform functions)
    This function uses the same transforms you already have (scale_point, shiftX, shiftY, trX, trY)
    and emits G1 moves with penDown/penUp. It will lower pen at first point and lift at end.
    """
    global isPenDown
    if not path_coords:
        return

    # Move to first point (pen up), then pen down and follow points
    px, py = path_coords[0]
    sx = scale_point(px) + shiftX
    sy = scale_point(h) - scale_point(py) + shiftY - scale_point(h) / 2
    x = trX(sx, sy, armL)
    y = trY(sx, sy, armL, rodS)

    # Rapid to starting point
    print("G1 X", x, " Y", y, " F", travelFeed, sep='', file=out)
    print(penDown, file=out)
    isPenDown = True

    for (px, py) in path_coords[1:]:
        sx = scale_point(px) + shiftX
        sy = scale_point(h) - scale_point(py) + shiftY - scale_point(h) / 2
        x = trX(sx, sy, armL)
        y = trY(sx, sy, armL, rodS)
        print("G1 X", x, " Y", y, " F", getFeed(), sep='', file=out)

    # lift at the end of this open polyline
    print(penUp, file=out)
    isPenDown = False

def resetOutputFile():
    global out
    out = open("output.nc", "w")

