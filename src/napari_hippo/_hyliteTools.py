"""

Some crunchy tools for data munging.

"""

from typing import TYPE_CHECKING
from qtpy.QtWidgets import QVBoxLayout, QPushButton, QWidget, QFrame, QGroupBox
import pathlib
if TYPE_CHECKING:
    import napari

import numpy as np
from magicgui import magicgui
import napari
from ._guiBase import GUIBase
from napari_hippo import getHyImage, h2n, n2h, getLayer, HSICube
import re
import hylite
from hylite.correct import get_hull_corrected
from hylite.filter import MNF, PCA
class HyliteToolsWidget(GUIBase):
    def __init__(self, napari_viewer):
        super().__init__(napari_viewer)

        self.calc_widget = magicgui( calculate, call_button='Calculate'  )
        self.stretch_widget = magicgui( stretch, call_button='Stretch',
                                        vmin=dict(min=-np.inf, max=np.inf, step=0.005),
                                        vmax=dict(min=-np.inf, max=np.inf, step=0.005),
                                        method={"choices": ['Absolute',
                                                            'Percent clip',
                                                            'Percent clip (per band)']} )
        self._add( [self.calc_widget, self.stretch_widget], 'Calculate and visualise' )


        self.hullCorrect_widget = magicgui(hullCorrect,
                                          wmin=dict(min=-np.inf, max=np.inf, step=1),
                                          wmax=dict(min=-np.inf, max=np.inf, step=1),
                                          call_button='Compute',
                                          auto_call=False)
        self._add([self.hullCorrect_widget], 'Hull Correction')

        self.dimensionReduction_widget = magicgui(dimensionReduction,
                                           method={"choices": ['PCA', 'MNF']},
                                           ndim={'min': 1, 'max': 100},
                                           wmin=dict(min=-np.inf, max=np.inf, step=1),
                                           wmax=dict(min=-np.inf, max=np.inf, step=1),
                                           call_button='Reduce',
                                           auto_call=False)
        self._add([self.dimensionReduction_widget], 'Dimension Reduction')

        # add spacer at the bottom of panel
        self.qvl.addStretch()

def runOnImages( func, expand=False, all=False, add=False, suffix='', **kwargs ):
    """
    Run the specified function on all selected images (or, if all = True, all images in layers).
    If expand is True, the function will be run on all images if there is no selection.
    """
    viewer = napari.current_viewer()  # get viewer
    layers = viewer.layers.selection
    if all or (expand and (len(layers) == 0)):
        layers = viewer.layers
    out = []
    for l in layers:
        I = getLayer(l)
        if isinstance(I, HSICube):
            image = I.toHyImage()
            image.decompress() # possibly important for int data types
            result = func(image, **kwargs)
            if result is not None:
                if add:
                    name = l.name + '(%s)'%suffix
                    out.append( HSICube.construct( result, name, viewer=viewer).layer )
                else:
                    I.fromHyImage(func(image, **kwargs)) # update in situ
                    out.append( l )
    if len(out) == 0:
        napari.utils.notifications.show_warning(
            "Could not find valid HSI data.")
    return out

def calculate( bands : str = "%d, %d, %d" % hylite.RGB ):
    """
    Evaluate simple mathematic band combinations (e.g., band ratios) to derive
    single-band or multi-band (false-colour composite) output images.

    Band combinations use a simple python-like text syntax, using the following additional notation:
        - 'b': flags that the following number is a band index (e.g. b10)
        - '$': flags that the following number is a constant (e.g., $2 )
        - ':': flags that bands between the previous and the following number should be averaged (e.g.
                2190:2210 averages all bands between 2190 nm and 2210 nm wavelengths)
        - all other numbers are treated as wavelengths
        - arithmetic operations +, -, / and * are all supported.
    """
    def op( image, bands ):
        # evaluate expression using hylite
        bands = bands.replace(',','|') # replace commas with new band symbol (|)
        return image.eval( bands )
    return runOnImages( op, add=True, suffix='calc', bands=bands)

def stretch( vmin : float = 2, vmax : float = 98,
             method : str = 'Percent clip (per band)' ):
    
    def op(image, method, vmin, vmax):
        # apply normalisation
        if method == 'Percent clip (per band)':
            image.percent_clip( int(vmin), int(vmax), per_band=True )
        elif method == 'Percent clip':
            image.percent_clip( int(vmin), int(vmax), per_band=False)
        elif method == 'Absolute':
            image.data = np.clip( (image.data - vmin) / (vmax-vmin), 0, 1 )
        return image
    layers = runOnImages( op, add=False, vmin=vmin, vmax=vmax, method=method)
    for l in layers:
        l.contrast_limits = (0,1) # also update contrast limits!
        l.contrast_limits_range = (0,1) # and slider range!
    return layers

def hullCorrect(wmin : float = 2000.,
                wmax : float = 2500.,
                upper : bool = True):
    def op(image, wmin,wmax,upper):
        if upper:
            return get_hull_corrected(image, band_range=(wmin, wmax), hull='upper')
        else:
            return get_hull_corrected(image, band_range=(wmin, wmax), hull='lower')
    return runOnImages( op, add=True, suffix='hc', wmin=wmin, wmax=wmax,upper=upper)

def dimensionReduction( method : str = 'PCA', ndim : int = 5, wmin : float = 2000., wmax : float = 2500. ):
    def op(image, method, ndim, wmin, wmax ):
        if 'mnf' in method.lower():
            R = MNF
        elif 'pca' in method.lower():
            R = PCA
        else:
            napari.utils.notifications.show_warning(
                "Warning: Unknown dimension reduction method %s."%method)
            return None
        brange = ( image.get_band_index(wmin), image.get_band_index(wmax) )
        return R( image, bands= ndim, band_range=brange )[0]
    return runOnImages( op, method=method, ndim=ndim, wmin=wmin, wmax=wmax, suffix=method,add=True)

