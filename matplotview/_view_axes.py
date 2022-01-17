import itertools
from typing import Type, List
from matplotlib.axes import Axes
from matplotlib.transforms import Bbox
import matplotlib.docstring as docstring
from matplotview._transform_renderer import _TransformRenderer
from matplotlib.artist import Artist
from matplotlib.backend_bases import RendererBase

class BoundRendererArtist:
    def __init__(self, artist: Artist, renderer: RendererBase, clip_box: Bbox):
        self._artist = artist
        self._renderer = renderer
        self._clip_box = clip_box

    def __getattribute__(self, item):
        try:
            return super().__getattribute__(item)
        except AttributeError:
            return self._artist.__getattribute__(item)

    def __setattr__(self, key, value):
        try:
            super().__setattr__(key, value)
        except AttributeError:
            self._artist.__setattr__(key, value)

    def draw(self, renderer: RendererBase):
        # Disable the artist defined clip box, as the artist might be visible
        # under the new renderer even if not on screen...
        clip_box_orig = self._artist.get_clip_box()
        full_extents = self._artist.get_window_extent(self._renderer)
        self._artist.set_clip_box(full_extents)

        # Check and see if the passed limiting box and extents of the
        # artist intersect, if not don't bother drawing this artist.
        if(Bbox.intersection(full_extents, self._clip_box) is not None):
            self._artist.draw(self._renderer)

        # Re-enable the clip box...
        self._artist.set_clip_box(clip_box_orig)


def view_wrapper(axes_class: Type[Axes]) -> Type[Axes]:
    """
    Construct a ViewAxes, which subclasses, or wraps a specific Axes subclass.
    A ViewAxes can be configured to display the contents of another Axes
    within the same Figure.

    Parameters
    ----------
    axes_class: Type[Axes]
        An axes type to construct a new ViewAxes wrapper class for.

    Returns
    -------
    ViewAxes:
        The view axes wrapper for a given axes class, capable of display
        other axes contents...
    """

    @docstring.interpd
    class ViewAxesImpl(axes_class):
        """
        An axes which automatically displays elements of another axes. Does not
        require Artists to be plotted twice.
        """
        __module__ = axes_class.__module__
        # The number of allowed recursions in the draw method
        MAX_RENDER_DEPTH = 5

        def __init__(
            self,
            axes_to_view: Axes,
            *args,
            image_interpolation: str = "nearest",
            **kwargs
        ):
            """
            Construct a new view axes.

            Parameters
            ----------
            axes_to_view: `~.axes.Axes`
                The axes to create a view of.

            *args
                Additional arguments to be passed to the Axes class this
                ViewAxes wraps.

            image_interpolation: string
                Supported options are 'antialiased', 'nearest', 'bilinear',
                'bicubic', 'spline16', 'spline36', 'hanning', 'hamming',
                'hermite', 'kaiser', 'quadric', 'catrom', 'gaussian', 'bessel',
                'mitchell', 'sinc', 'lanczos', or 'none'. The default value is
                'nearest'. This determines the interpolation used when
                attempting to render a view of an image.

            **kwargs
                Other optional keyword arguments supported by the Axes
                constructor this ViewAxes wraps:

                %(Axes:kwdoc)s

            Returns
            -------
            ViewAxes
                The new zoom view axes instance...
            """
            super().__init__(axes_to_view.figure, *args, **kwargs)
            self._init_vars(axes_to_view, image_interpolation)

        def _init_vars(
            self,
            axes_to_view: Axes,
            image_interpolation: str = "nearest"
        ):
            self.__view_axes = axes_to_view
            self.__image_interpolation = image_interpolation
            self._render_depth = 0
            self.__scale_lines = True
            self.__renderer = None

        def get_children(self) -> List[Artist]:
            # We overload get_children to return artists from the view axes
            # in addition to this axes when drawing. We wrap the artists
            # in a BoundRendererArtist, so they are drawn with an alternate
            # renderer, and therefore to the correct location.
            if(self.__renderer is not None):
                mock_renderer = _TransformRenderer(
                    self.__renderer, self.__view_axes.transData,
                    self.transData, self, self.__image_interpolation,
                    self.__scale_lines
                )

                x1, x2 = self.get_xlim()
                y1, y2 = self.get_ylim()
                axes_box = Bbox.from_extents(x1, y1, x2, y2).transformed(
                    self.__view_axes.transData
                )

                init_list = super().get_children()
                init_list.extend([
                    BoundRendererArtist(a, mock_renderer, axes_box)
                    for a in itertools.chain(
                        self.__view_axes._children, self.__view_axes.child_axes
                    ) if(a is not self)
                ])

                return init_list
            else:
                return super().get_children()
            
        def draw(self, renderer: RendererBase = None):
            # It is possible to have two axes which are views of each other
            # therefore we track the number of recursions and stop drawing
            # at a certain depth
            if(self._render_depth >= self.MAX_RENDER_DEPTH):
                return
            self._render_depth += 1
            # Set the renderer, causing get_children to return the view's
            # children also...
            self.__renderer = renderer

            super().draw(renderer)

            # Get rid of the renderer...
            self.__renderer = None
            self._render_depth -= 1

        def get_linescaling(self) -> bool:
            """
            Get if line width scaling is enabled.

            Returns
            -------
            bool
                If line width scaling is enabled returns True, otherwise False.
            """
            return self.__scale_lines

        def set_linescaling(self, value: bool):
            """
            Set whether line widths should be scaled when rendering a view of
            an axes.

            Parameters
            ----------
            value: bool
                If true, scale line widths in the view to match zoom level.
                Otherwise don't.
            """
            self.__scale_lines = value

        @classmethod
        def from_axes(
            cls,
            axes: Axes,
            axes_to_view: Axes,
            image_interpolation: str = "nearest"
        ):
            axes.__class__ = cls
            axes._init_vars(axes_to_view, image_interpolation)
            return axes

    new_name = f"{ViewAxesImpl.__name__}[{axes_class.__name__}]"
    ViewAxesImpl.__name__ = ViewAxesImpl.__qualname__ = new_name

    return ViewAxesImpl


ViewAxes = view_wrapper(Axes)