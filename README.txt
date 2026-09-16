This software is intended for use with the delta pen plotter machine shown here: https://youtu.be/IRmwhncLU2s

The original GitHub page of the program is the following: https://github.com/vujoboy/Delta-Plotter-Path-Generator

The design of this plotter can be bought here: https://www.printables.com/model/1843433-delta-plotter-with-auto-tool-chnager

### Delta Plotter Path Generator software workflow ###

1) Select a project folder. If want to work on previously created drawing project select an existing project folder. If you want to start a new project instead create a new project folder. In this folder an XML save file will be created.

2) Place input images or SVGs in the project folder.

3) Browse in input image for your first laser.

4) Select path generation mode.

5) Set parameters. Pen slot number for layer, feed rate, and other path generation mode specific options.

6) Click Save XML & Update View button.

7) This will generate an output.nc file in your project folder.

8) Open the output.nc file in your g-code/NC code sender and visually verify. I recommend using gSender.

9) Run path from your g-code/NC code sender.
