from styx_msgs.msg import TrafficLight
import rospy
import cv2
import tensorflow as tf
import numpy as np
from PIL import Image
from PIL import ImageDraw
from PIL import ImageColor
from datetime import datetime

SSD_GRAPH_FILE = 'ssd_mobilenet_v1_coco_11_06_2017/frozen_inference_graph.pb'

boundaries = [
    ([0, 43, 46], [10, 255, 255]), # red
    ([26, 43, 46], [34, 255, 255]), # yellow
    ([35, 43, 46], [77, 255, 255])] # green

COLOR_LIST = ['red', 'yellow', 'green']

def filter_boxes(min_score, boxes, scores, classes):
    """Return boxes with a confidence >= `min_score`"""
    n = len(classes)
    idxs = []
    for i in range(n):
        if scores[i] >= min_score and classes[i] == 10: # https://github.com/tensorflow/models/blob/master/research/object_detection/data/mscoco_label_map.pbtxt
            idxs.append(i)
 
    filtered_boxes = boxes[idxs, ...]
    filtered_scores = scores[idxs, ...]
    filtered_classes = classes[idxs, ...]
    return filtered_boxes, filtered_scores, filtered_classes

def to_image_coords(boxes, height, width):
    """
    The original box coordinate output is normalized, i.e [0, 1].
 
    This converts it back to the original coordinate based on the image
    size.
    """
    box_coords = np.zeros_like(boxes)
    box_coords[:, 0] = boxes[:, 0] * height
    box_coords[:, 1] = boxes[:, 1] * width
    box_coords[:, 2] = boxes[:, 2] * height
    box_coords[:, 3] = boxes[:, 3] * width

    return box_coords

def draw_boxes(image, boxes, classes, scores, color_id, thickness=4):
    """Draw bounding boxes on the image"""
    draw = ImageDraw.Draw(image)
    for i in range(len(boxes)):
        bot, left, top, right = boxes[i, ...]
        class_id = int(classes[i])
        color = COLOR_LIST[color_id]
        
        draw.line([(left, top), (left, bot), (right, bot), (right, top), (left, top)], width=thickness, fill=color)

def load_graph(graph_file):
    """Loads a frozen inference graph"""
    graph = tf.Graph()
    with graph.as_default():
        od_graph_def = tf.GraphDef()
        with tf.gfile.GFile(graph_file, 'rb') as fid:
            serialized_graph = fid.read()
            od_graph_def.ParseFromString(serialized_graph)
            tf.import_graph_def(od_graph_def, name='')
    return graph


class TLClassifier(object):
    def __init__(self):
        #TODO load classifier
        rospy.logwarn("load model file: %s", SSD_GRAPH_FILE)
        self.detection_graph = load_graph(SSD_GRAPH_FILE)

        # The input placeholder for the image.
        # `get_tensor_by_name` returns the Tensor with the associated name in the Graph.
        self.image_tensor = self.detection_graph.get_tensor_by_name('image_tensor:0')

        # Each box represents a part of the image where a particular object was detected.
        self.detection_boxes = self.detection_graph.get_tensor_by_name('detection_boxes:0')

        # Each score represent how level of confidence for each of the objects.
        # Score is shown on the result image, together with the class label.
        self.detection_scores = self.detection_graph.get_tensor_by_name('detection_scores:0')

        # The classification of the object (integer id).
        self.detection_classes = self.detection_graph.get_tensor_by_name('detection_classes:0')

        with tf.Session(graph=self.detection_graph) as sess:
            self.session = sess

    def get_classification(self, image):
        """Determines the color of the traffic light in the image

        Args:
            image (cv::Mat): image containing the traffic light

        Returns:
            int: ID of traffic light color (specified in styx_msgs/TrafficLight)

        """
        #TODO implement light color prediction
        # return TrafficLight.UNKNOWN

        color = TrafficLight.UNKNOWN
        
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image_np = np.expand_dims(np.asarray(image, dtype=np.uint8), 0)
              
        # Actual detection.
        (boxes, scores, classes) = self.session.run([self.detection_boxes, self.detection_scores, self.detection_classes], 
                                            feed_dict={self.image_tensor: image_np})

        # Remove unnecessary dimensions
        boxes = np.squeeze(boxes)
        scores = np.squeeze(scores)
        classes = np.squeeze(classes)

        confidence_cutoff = 0.2
        # Filter boxes with a confidence score less than `confidence_cutoff`
        boxes, scores, classes = filter_boxes(confidence_cutoff, boxes, scores, classes)

        if len(boxes) > 0:
            # The current box coordinates are normalized to a range between 0 and 1.
            # This converts the coordinates actual location on the image.
            width, height = image.shape[-2::-1]
            box_coords = to_image_coords(boxes, height, width)
            # Save the color for each state
            light_color = [0,0,0]
            for i in range(len(box_coords)):
                bot, left, top, right = box_coords[i, ...]
                box_img = image[int(bot):int(top), int(left):int(right), :]

                box_img = cv2.GaussianBlur(box_img, (3, 3), 0)

                hsv = cv2.cvtColor(box_img, cv2.COLOR_RGB2HSV)
                mask = [0,0,0]
                for j, (lowest, highest) in enumerate(boundaries):
                    # create NumPy arrays from the boundaries
                    lowest = np.array(lowest, dtype = "uint8")
                    highest = np.array(highest, dtype = "uint8")

                    # sum the color between the lowest and highest in the mask
                    mask[j] = sum(np.hstack(cv2.inRange(hsv, lowest, highest)))
                # the maximum value of the item in mask is considered to be the corresponding color
                light_color[mask.index(max(mask))] += 1 
            # the index of the maximum value of the item in light_color is the light color
            color = light_color.index(max(light_color))

        rospy.logwarn('detected light = %d', color)
        return color
