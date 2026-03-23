import gxipy as gx
import numpy as np
import time
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage
from gxipy.gxidef import *
from gxipy.ImageFormatConvert import *
from PIL import Image
from ctypes import *


def get_camera_list():
    global device_manager
    if 'device_manager' not in globals():
        device_manager = gx.DeviceManager()
    dev_num, dev_info_list = device_manager.update_all_device_list()
    if dev_num == 0:
        raise RuntimeError("No Daheng cameras found")
    return dev_info_list


class DahengCamera(QObject):
    frame_ready = Signal(object)  # pass QImage

    def __init__(self,  exposure_time=10000.0):
        super(DahengCamera, self).__init__()
        self.running = False
        self.camera = None
        self.remote_device_feature = None
        self.data_stream = None
        self.image_convert = None
        self.exposure_time = exposure_time
        self.trigger_software_command_feature = None
        self.camera_sn = ''
        self.roi = None

    def set_camera_param(self, param):
        self.camera_sn = param

    def initialize(self):
        try:
            # Open the device by sn
            self.camera = device_manager.open_device_by_sn(self.camera_sn)

            # Configure camera settings
            self.remote_device_feature = self.camera.get_remote_device_feature_control()
            # remote_device_feature.get_float_feature(
            #     "ExposureTime").set(self.exposure_time)

            self.image_convert = device_manager.create_image_format_convert()

            # set exposure
            exposure_time_feature = self.remote_device_feature.get_float_feature(
                "ExposureTime")
            exposure_time_feature.set(self.exposure_time)

            trigger_mode_feature = self.remote_device_feature.get_enum_feature(
                "TriggerMode")
            # 如果是 on 就得手动发送 self.trigger_software_command_feature.send_command() ，否则不需要
            trigger_mode_feature.set("On")
            trigger_source_feature = self.remote_device_feature.get_enum_feature(
                "TriggerSource")
            trigger_source_feature.set("Software")
            self.trigger_software_command_feature = self.remote_device_feature.get_command_feature(
                "TriggerSoftware")

            # get datastream
            self.data_stream = self.camera.data_stream[0]

            pixel_format_value, pixel_format_str = self.remote_device_feature.get_enum_feature(
                "PixelFormat").get()
            if Utility.is_gray(pixel_format_value):
                self.camera.close_device()
                raise Exception("Camera does not support mono color.")
            else:
                self.data_stream.register_capture_callback(
                    lambda raw_image: self._capture_callback(raw_image))

            return True
        except Exception as e:
            print(f"Camera initialization error: {str(e)}")
            return False

    def _capture_callback(self, raw_image):
        if raw_image is None:
            return

        try:
            # print height, width, and frame ID of the acquisition image
            # print("Frame ID: %d   Height: %d   Width: %d"
            #       % (raw_image.get_frame_id(), raw_image.get_height(), raw_image.get_width()))

            if raw_image.get_pixel_format() != GxPixelFormatEntry.RGB8:
                # 当前相机进到这里
                rgb_image_array, rgb_image_buffer_length = self.convert_to_special_pixel_format(raw_image,
                                                                                                GxPixelFormatEntry.RGB8)
                if rgb_image_array is None:
                    return

                # create numpy array with data from rgb image
                numpy_image = numpy.frombuffer(rgb_image_array, dtype=numpy.ubyte, count=rgb_image_buffer_length). \
                    reshape(raw_image.frame_data.height,
                            raw_image.frame_data.width, 3)
            else:
                numpy_image = raw_image.get_numpy_array()

            if numpy_image is None:
                print('Failed to get numpy array from RGBImage')
                return

            # Apply ROI if set
            numpy_image = self.apply_roi_not_recommend(numpy_image)

            # show acquired image
            # frame = Image.fromarray(numpy_image, 'RGB')
            height, width, channel = numpy_image.shape
            bytes_per_line = channel * width
            q_image = QImage(numpy_image.data, width, height,
                             bytes_per_line, QImage.Format_RGB888)

            if q_image is not None and self.running:
                self.frame_ready.emit(q_image)

            self.trigger_software_command_feature.send_command()

        except Exception as e:
            print(f"Frame callback error: {str(e)}")
        finally:
            pass
            # raw_image.release()

    def start(self):
        if self.initialize():
            self.running = True
            self.camera.stream_on()

            print('<Start acquisition>')
            time.sleep(0.1)
            self.trigger_software_command_feature.send_command()

    def stop(self):
        self.running = False
        if self.camera:
            self.camera.stream_off()
            self.data_stream.unregister_capture_callback()
        self._cleanup()

    def _cleanup(self):
        if self.camera:
            self.camera.close_device()
            self.camera = None

        self.data_stream = None
        self.image_convert = None

    def get_best_valid_bits(self, pixel_format):
        valid_bits = DxValidBit.BIT0_7
        if pixel_format in (GxPixelFormatEntry.MONO8, GxPixelFormatEntry.BAYER_GR8, GxPixelFormatEntry.BAYER_RG8,
                            GxPixelFormatEntry.BAYER_GB8, GxPixelFormatEntry.BAYER_BG8, GxPixelFormatEntry.RGB8, GxPixelFormatEntry.BGR8, GxPixelFormatEntry.R8,
                            GxPixelFormatEntry.B8, GxPixelFormatEntry.G8):
            valid_bits = DxValidBit.BIT0_7
        elif pixel_format in (
                GxPixelFormatEntry.MONO10, GxPixelFormatEntry.MONO10_PACKED, GxPixelFormatEntry.BAYER_GR10,
                GxPixelFormatEntry.BAYER_RG10, GxPixelFormatEntry.BAYER_GB10, GxPixelFormatEntry.BAYER_BG10):
            valid_bits = DxValidBit.BIT2_9
        elif pixel_format in (
                GxPixelFormatEntry.MONO12, GxPixelFormatEntry.MONO12_PACKED, GxPixelFormatEntry.BAYER_GR12,
                GxPixelFormatEntry.BAYER_RG12, GxPixelFormatEntry.BAYER_GB12, GxPixelFormatEntry.BAYER_BG12):
            valid_bits = DxValidBit.BIT4_11
        elif pixel_format in GxPixelFormatEntry.MONO14:
            valid_bits = DxValidBit.BIT6_13
        elif pixel_format in GxPixelFormatEntry.MONO16:
            valid_bits = DxValidBit.BIT8_15
        return valid_bits

    def convert_to_special_pixel_format(self, raw_image, pixel_format):
        self.image_convert.set_dest_format(pixel_format)
        valid_bits = self.get_best_valid_bits(raw_image.get_pixel_format())
        self.image_convert.set_valid_bits(valid_bits)

        # create out put image buffer
        buffer_out_size = self.image_convert.get_buffer_size_for_conversion(
            raw_image)
        output_image_array = (c_ubyte * buffer_out_size)()
        output_image = addressof(output_image_array)

        # convert to pixel_format
        self.image_convert.convert(
            raw_image, output_image, buffer_out_size, False)
        if output_image is None:
            print('Pixel format conversion failed')
            return

        return output_image_array, buffer_out_size

    def set_roi(self, roi_dict):
        print(f"Setting ROI: {roi_dict}")
        # Implement the logic to handle the ROI setting
        # For example, you might want to update the camera's region of interest

        self.roi = roi_dict

        return

        if roi_dict:
            startx = int(roi_dict['startx'])
            starty = int(roi_dict['starty'])
            width = int(roi_dict['width'])
            height = int(roi_dict['height'])

            self.remote_device_feature.get_int_feature(
                "OffsetX").set(startx)
            self.remote_device_feature.get_int_feature(
                "OffsetY").set(starty)
            self.remote_device_feature.get_int_feature(
                "Width").set(width)
            self.remote_device_feature.get_int_feature(
                "Height").set(height)
        else:
            WidthMax = self.remote_device_feature.get_int_feature(
                "WidthMax")
            HeightMax = self.remote_device_feature.get_int_feature(
                "HeightMax")
            self.remote_device_feature.get_int_feature(
                "OffsetX").set(0)
            self.remote_device_feature.get_int_feature(
                "OffsetY").set(0)
            self.remote_device_feature.get_int_feature(
                "Width").set(WidthMax)
            self.remote_device_feature.get_int_feature(
                "Height").set(HeightMax)

    def __del__(self):
        self.stop()
        print("DahengCamera instance deleted!")
