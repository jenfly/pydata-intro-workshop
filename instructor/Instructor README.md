# Notes for Instructor

These notebooks use the `RISE` library to convert Jupyter notebooks into interactive slideshows:
- http://rise.readthedocs.io/en/latest/installation.html
```
conda install -c damianavila82 rise
```

Currently, `RISE` does **not** work in Jupyter Lab. You need to open these notebooks from a standalone Jupyter Notebook server (launch from Anaconda Navigator, or with the command `jupyter notebook` from the command prompt).

For the file paths to work, you need to move the Jupyter notebooks (`*.ipynb`) and `rise.css` up to the main project folder, or make copies of the `data` and `img` folders within the `instructor` folder.

To present the slideshow as a live demo, use the commands in the "Kernel" menu or "Cell" menu to clear the output of all cells.
