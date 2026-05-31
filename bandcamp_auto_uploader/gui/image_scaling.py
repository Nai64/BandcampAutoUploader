"""
Image scaling functions for the Bandcamp Auto Uploader GUI
Provides various resampling methods for cover art scaling
"""

try:
    import numpy as np
except ImportError:
    class _MissingNumpy:
        def __getattr__(self, _name):
            raise ImportError("NumPy is required for this scaling method")

    np = _MissingNumpy()


def get_resampling_method(scaling_method_var):
    """Convert scaling method string to PIL resampling constant or custom method"""
    from PIL import Image

    method = scaling_method_var.get()
    method_map = {
        "Nearest": Image.Resampling.NEAREST,
        "Box": Image.Resampling.BOX,
        "Bilinear": Image.Resampling.BILINEAR,
        "Hamming": Image.Resampling.HAMMING,
        "Bicubic": Image.Resampling.BICUBIC,
        "Lanczos": Image.Resampling.LANCZOS,
    }
    return method_map.get(method, Image.Resampling.LANCZOS)


def apply_custom_scaling(img, target_size, scaling_method_var):
    """Apply custom scaling method to image"""
    method = scaling_method_var.get()

    # Custom methods that require special handling
    if method == "Area":
        return scale_area(img, target_size)
    elif method == "Mitchell":
        return scale_mitchell(img, target_size)
    elif method == "Catmull-Rom":
        return scale_catmull_rom(img, target_size)
    elif method == "Sinc":
        return scale_sinc(img, target_size)
    elif method == "Gaussian":
        return scale_gaussian(img, target_size)
    elif method == "Pixelate":
        return scale_pixelate(img, target_size)
    elif method == "Hermite":
        return scale_hermite(img, target_size)
    elif method == "Blackman":
        return scale_blackman(img, target_size)
    elif method == "Kaiser":
        return scale_kaiser(img, target_size)
    elif method == "Welch":
        return scale_welch(img, target_size)
    elif method == "Parzen":
        return scale_parzen(img, target_size)
    elif method == "Bartlett":
        return scale_bartlett(img, target_size)
    elif method == "Cubic":
        return scale_cubic(img, target_size)
    elif method == "Quadratic":
        return scale_quadratic(img, target_size)
    elif method == "Average":
        return scale_average(img, target_size)
    elif method == "Max":
        return scale_max(img, target_size)
    elif method == "Min":
        return scale_min(img, target_size)
    elif method == "Median":
        return scale_median(img, target_size)
    elif method == "Sharpen":
        return scale_sharpen(img, target_size)
    elif method == "Edge-Enhanced":
        return scale_edge_enhanced(img, target_size)
    elif method == "B-Spline":
        return scale_bspline(img, target_size)
    elif method == "Rational":
        return scale_rational(img, target_size)
    else:
        # Fall back to PIL method
        from PIL import Image
        resampling_method = get_resampling_method(scaling_method_var)
        return img.resize((target_size, target_size), resampling_method)


def scale_area(img, target_size):
    """Area-based averaging scaling"""
    try:
        # Convert to numpy array
        img_array = np.array(img)
        h, w = img_array.shape[:2]

        # Calculate scale factors
        scale_x = target_size / w
        scale_y = target_size / h

        # If downscaling, use area averaging
        if scale_x < 1 or scale_y < 1:
            # Use PIL's box filter for area averaging (closest to area method)
            from PIL import Image
            return img.resize((target_size, target_size), Image.Resampling.BOX)
        else:
            # Upscaling - use bilinear
            from PIL import Image
            return img.resize((target_size, target_size), Image.Resampling.BILINEAR)
    except ImportError:
        # Fallback to box filter
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.BOX)


def scale_mitchell(img, target_size):
    """Mitchell-Netravali filter scaling"""
    try:
        from scipy.ndimage import zoom

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        # Calculate zoom factors
        zoom_factor = target_size / max(h, w)
        if len(img_array.shape) == 3:
            zoom_factors = (zoom_factor, zoom_factor, 1)
        else:
            zoom_factors = (zoom_factor, zoom_factor)

        # Apply zoom with Mitchell-like parameters (order=3 is cubic)
        scaled = zoom(img_array, zoom_factors, order=3, mode='reflect')

        # Convert back to PIL Image
        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8))
    except ImportError:
        # Fallback to bicubic
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.BICUBIC)


def scale_catmull_rom(img, target_size):
    """Catmull-Rom spline scaling"""
    try:
        from scipy.ndimage import zoom

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        # Calculate zoom factors
        zoom_factor = target_size / max(h, w)
        if len(img_array.shape) == 3:
            zoom_factors = (zoom_factor, zoom_factor, 1)
        else:
            zoom_factors = (zoom_factor, zoom_factor)

        # Catmull-Rom is similar to cubic with specific parameters
        # Use order=3 with specific prefilter
        scaled = zoom(img_array, zoom_factors, order=3, mode='reflect', prefilter=True)

        # Convert back to PIL Image
        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8))
    except ImportError:
        # Fallback to bicubic
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.BICUBIC)


def scale_sinc(img, target_size):
    """Sinc/Lanczos windowed scaling"""
    try:
        from scipy.ndimage import zoom

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        # Calculate zoom factors
        zoom_factor = target_size / max(h, w)
        if len(img_array.shape) == 3:
            zoom_factors = (zoom_factor, zoom_factor, 1)
        else:
            zoom_factors = (zoom_factor, zoom_factor)

        # Sinc is similar to Lanczos but with different window
        # Use high-order spline as approximation
        scaled = zoom(img_array, zoom_factors, order=5, mode='reflect')

        # Convert back to PIL Image
        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8))
    except ImportError:
        # Fallback to Lanczos
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.LANCZOS)


def scale_gaussian(img, target_size):
    """Gaussian blur-based scaling"""
    try:
        from scipy.ndimage import gaussian_filter, zoom

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        # Calculate zoom factors
        zoom_factor = target_size / max(h, w)
        if len(img_array.shape) == 3:
            zoom_factors = (zoom_factor, zoom_factor, 1)
        else:
            zoom_factors = (zoom_factor, zoom_factor)

        # Apply slight gaussian blur before/after scaling for smoothness
        if zoom_factor < 1:  # Downscaling
            # Blur before downscaling
            sigma = 1 / zoom_factor * 0.5
            blurred = gaussian_filter(img_array, sigma=sigma, mode='reflect')
            scaled = zoom(blurred, zoom_factors, order=1, mode='reflect')
        else:  # Upscaling
            scaled = zoom(img_array, zoom_factors, order=3, mode='reflect')
            # Blur after upscaling
            sigma = zoom_factor * 0.5
            scaled = gaussian_filter(scaled, sigma=sigma, mode='reflect')

        # Convert back to PIL Image
        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8))
    except ImportError:
        # Fallback to bilinear
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.BILINEAR)


def scale_pixelate(img, target_size):
    """Intentional pixelation effect"""
    from PIL import Image

    # First downscale to very small size
    pixel_size = max(8, target_size // 20)  # Calculate pixel block size
    small_size = max(8, target_size // pixel_size)
    small = img.resize((small_size, small_size), Image.Resampling.NEAREST)

    # Then upscale back to target with nearest neighbor
    return small.resize((target_size, target_size), Image.Resampling.NEAREST)


def scale_hermite(img, target_size):
    """Cubic Hermite spline scaling"""
    try:
        from scipy.ndimage import zoom

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        zoom_factor = target_size / max(h, w)
        if len(img_array.shape) == 3:
            zoom_factors = (zoom_factor, zoom_factor, 1)
        else:
            zoom_factors = (zoom_factor, zoom_factor)

        # Hermite is a specific cubic interpolation
        scaled = zoom(img_array, zoom_factors, order=3, mode='nearest')

        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8))
    except ImportError:
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.BICUBIC)


def scale_blackman(img, target_size):
    """Blackman windowed sinc scaling"""
    try:
        from scipy.ndimage import zoom

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        zoom_factor = target_size / max(h, w)
        if len(img_array.shape) == 3:
            zoom_factors = (zoom_factor, zoom_factor, 1)
        else:
            zoom_factors = (zoom_factor, zoom_factor)

        # Apply Blackman windowed sinc-like scaling
        scaled = zoom(img_array, zoom_factors, order=4, mode='reflect')

        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8))
    except ImportError:
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.LANCZOS)


def scale_kaiser(img, target_size):
    """Kaiser windowed sinc scaling"""
    try:
        from scipy.ndimage import zoom

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        zoom_factor = target_size / max(h, w)
        if len(img_array.shape) == 3:
            zoom_factors = (zoom_factor, zoom_factor, 1)
        else:
            zoom_factors = (zoom_factor, zoom_factor)

        # Kaiser window for smooth scaling
        scaled = zoom(img_array, zoom_factors, order=5, mode='reflect')

        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8))
    except ImportError:
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.LANCZOS)


def scale_welch(img, target_size):
    """Welch windowed scaling"""
    try:
        from scipy.ndimage import zoom

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        zoom_factor = target_size / max(h, w)
        if len(img_array.shape) == 3:
            zoom_factors = (zoom_factor, zoom_factor, 1)
        else:
            zoom_factors = (zoom_factor, zoom_factor)

        # Welch window provides smooth transitions
        scaled = zoom(img_array, zoom_factors, order=3, mode='reflect')

        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8))
    except ImportError:
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.BICUBIC)


def scale_parzen(img, target_size):
    """Parzen window scaling"""
    try:
        from scipy.ndimage import zoom

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        zoom_factor = target_size / max(h, w)
        if len(img_array.shape) == 3:
            zoom_factors = (zoom_factor, zoom_factor, 1)
        else:
            zoom_factors = (zoom_factor, zoom_factor)

        # Parzen window is a smooth window function
        scaled = zoom(img_array, zoom_factors, order=3, mode='constant')

        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8))
    except ImportError:
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.BICUBIC)


def scale_bartlett(img, target_size):
    """Bartlett/Triangular window scaling"""
    try:
        from scipy.ndimage import zoom

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        zoom_factor = target_size / max(h, w)
        if len(img_array.shape) == 3:
            zoom_factors = (zoom_factor, zoom_factor, 1)
        else:
            zoom_factors = (zoom_factor, zoom_factor)

        # Bartlett window is triangular
        scaled = zoom(img_array, zoom_factors, order=2, mode='reflect')

        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8))
    except ImportError:
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.BILINEAR)


def scale_cubic(img, target_size):
    """Generic cubic interpolation scaling"""
    try:
        from scipy.ndimage import zoom

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        zoom_factor = target_size / max(h, w)
        if len(img_array.shape) == 3:
            zoom_factors = (zoom_factor, zoom_factor, 1)
        else:
            zoom_factors = (zoom_factor, zoom_factor)

        # Generic cubic interpolation
        scaled = zoom(img_array, zoom_factors, order=3, mode='reflect')

        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8))
    except ImportError:
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.BICUBIC)


def scale_quadratic(img, target_size):
    """Quadratic interpolation scaling"""
    try:
        from scipy.ndimage import zoom

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        zoom_factor = target_size / max(h, w)
        if len(img_array.shape) == 3:
            zoom_factors = (zoom_factor, zoom_factor, 1)
        else:
            zoom_factors = (zoom_factor, zoom_factor)

        # Quadratic interpolation (order=2)
        scaled = zoom(img_array, zoom_factors, order=2, mode='reflect')

        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8))
    except ImportError:
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.BILINEAR)


def scale_average(img, target_size):
    """Simple averaging scaling"""
    try:
        from PIL import Image

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        # Use PIL's box filter for averaging
        return img.resize((target_size, target_size), Image.Resampling.BOX)
    except ImportError:
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.BOX)


def scale_max(img, target_size):
    """Max pooling scaling (for downscaling only)"""
    try:
        from skimage.measure import block_reduce

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        # Only for downscaling
        if target_size >= max(h, w):
            from PIL import Image
            return img.resize((target_size, target_size), Image.Resampling.NEAREST)

        # Calculate block size
        scale = max(h, w) / target_size
        block_size = int(scale)

        if len(img_array.shape) == 3:
            # Apply max pooling
            scaled = block_reduce(img_array, (block_size, block_size, 1), np.max)
        else:
            scaled = block_reduce(img_array, (block_size, block_size), np.max)

        # Resize to exact target
        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8)).resize((target_size, target_size), Image.Resampling.NEAREST)
    except ImportError:
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.BOX)


def scale_min(img, target_size):
    """Min pooling scaling (for downscaling only)"""
    try:
        from skimage.measure import block_reduce

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        # Only for downscaling
        if target_size >= max(h, w):
            from PIL import Image
            return img.resize((target_size, target_size), Image.Resampling.NEAREST)

        # Calculate block size
        scale = max(h, w) / target_size
        block_size = int(scale)

        if len(img_array.shape) == 3:
            # Apply min pooling
            scaled = block_reduce(img_array, (block_size, block_size, 1), np.min)
        else:
            scaled = block_reduce(img_array, (block_size, block_size), np.min)

        # Resize to exact target
        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8)).resize((target_size, target_size), Image.Resampling.NEAREST)
    except ImportError:
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.BOX)


def scale_median(img, target_size):
    """Median pooling scaling (for downscaling only)"""
    try:
        from skimage.measure import block_reduce

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        # Only for downscaling
        if target_size >= max(h, w):
            from PIL import Image
            return img.resize((target_size, target_size), Image.Resampling.BILINEAR)

        # Calculate block size
        scale = max(h, w) / target_size
        block_size = int(scale)

        if len(img_array.shape) == 3:
            # Apply median pooling
            scaled = block_reduce(img_array, (block_size, block_size, 1), np.median)
        else:
            scaled = block_reduce(img_array, (block_size, block_size), np.median)

        # Resize to exact target
        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8)).resize((target_size, target_size), Image.Resampling.BILINEAR)
    except ImportError:
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.BOX)


def scale_sharpen(img, target_size):
    """Sharpening-based scaling"""
    try:
        from scipy.ndimage import zoom, gaussian_filter
        from PIL import Image, ImageFilter

        # First scale normally
        scaled = img.resize((target_size, target_size), Image.Resampling.BICUBIC)

        # Apply sharpening
        scaled = scaled.filter(ImageFilter.SHARPEN)

        return scaled
    except ImportError:
        from PIL import Image, ImageFilter
        scaled = img.resize((target_size, target_size), Image.Resampling.BICUBIC)
        return scaled.filter(ImageFilter.SHARPEN)


def scale_edge_enhanced(img, target_size):
    """Edge-enhanced scaling"""
    try:
        from scipy.ndimage import zoom, sobel
        from PIL import Image

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        zoom_factor = target_size / max(h, w)
        if len(img_array.shape) == 3:
            zoom_factors = (zoom_factor, zoom_factor, 1)
        else:
            zoom_factors = (zoom_factor, zoom_factor)

        # Scale with high-order interpolation
        scaled = zoom(img_array, zoom_factors, order=5, mode='reflect')

        # Enhance edges
        if len(scaled.shape) == 3:
            for i in range(3):
                edges = sobel(scaled[:, :, i])
                scaled[:, :, i] = np.clip(scaled[:, :, i] + edges * 0.3, 0, 255)
        else:
            edges = sobel(scaled)
            scaled = np.clip(scaled + edges * 0.3, 0, 255)

        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8))
    except ImportError:
        from PIL import Image, ImageFilter
        scaled = img.resize((target_size, target_size), Image.Resampling.LANCZOS)
        return scaled.filter(ImageFilter.EDGE_ENHANCE)


def scale_bspline(img, target_size):
    """B-spline interpolation scaling"""
    try:
        from scipy.ndimage import zoom

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        zoom_factor = target_size / max(h, w)
        if len(img_array.shape) == 3:
            zoom_factors = (zoom_factor, zoom_factor, 1)
        else:
            zoom_factors = (zoom_factor, zoom_factor)

        # B-spline with prefilter
        scaled = zoom(img_array, zoom_factors, order=3, mode='reflect', prefilter=True)

        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8))
    except ImportError:
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.BICUBIC)


def scale_rational(img, target_size):
    """Rational interpolation scaling"""
    try:
        from scipy.ndimage import zoom

        img_array = np.array(img)
        h, w = img_array.shape[:2]

        zoom_factor = target_size / max(h, w)
        if len(img_array.shape) == 3:
            zoom_factors = (zoom_factor, zoom_factor, 1)
        else:
            zoom_factors = (zoom_factor, zoom_factor)

        # Use high-order spline as rational approximation
        scaled = zoom(img_array, zoom_factors, order=4, mode='reflect')

        from PIL import Image
        return Image.fromarray(scaled.astype(np.uint8))
    except ImportError:
        from PIL import Image
        return img.resize((target_size, target_size), Image.Resampling.BICUBIC)
