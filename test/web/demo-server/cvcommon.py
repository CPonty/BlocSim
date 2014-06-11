# Utility functions for working with OpenCV library

from math import hypot
from random import random
import numpy as np
import cv2

cv2_blue = (255,0,0)
cv2_green = (0,255,0)
cv2_red = (0,0,255)
cv2_yellow = (0,255,255)
cv2_purple = (255,0,255)
cv2_white = (255,255,255)
cv2_black = (0,0,0)

cv2_pointMid = lambda (p1,p2): ((p1[0]+p2[0])/2.0, (p1[1]+p2[1])/2.0)
cv2_pointDiff = lambda (p1,p2): (p1[0]-p2[0], p1[1]-p2[1])
cv2_pointDiffs = lambda pts: map(cv2_pointDiff, zip(pts,pts[1:]))
cv2_pointDist = lambda ptDiff: hypot(*ptDiff)
cv2_pathDist = lambda path: [cv2_pointDist(d) for d in cv2_pointDiffs(path)]

"""
Given the points of a cv2.minAreaRect, return information about its major
and minor axes. w (width) is the minor axis.
"""
def cv2_minRectAxes(points):
    if (points.shape != (4,2)):
        raise ValueError("cv2_minRectW: 'points' should be np.array of shape"+\
                         " (4,2)")
    path = np.vstack((points,points[0,:]))
    pathDist = cv2_pathDist(path)
    sortedIdx = np.argsort(pathDist)
    #pathDistSorted = list(pathDist)
    #pathDistSorted.sort()
    (w,h) = pathDist[sortedIdx[0]], pathDist[sortedIdx[3]]

    def joinMidpoints(pathIdx1,pathIdx2):
        line1 = (path[pathIdx1], path[(pathIdx1+1)%4])
        line2 = (path[pathIdx2], path[(pathIdx2+1)%4])
        pt1 = tuple(np.int0(cv2_pointMid(line1)))
        pt2 = tuple(np.int0(cv2_pointMid(line2)))
        return (pt1, pt2)

    wline = joinMidpoints(sortedIdx[2], sortedIdx[3])
    hline = joinMidpoints(sortedIdx[0], sortedIdx[1])
    return (w,h),wline,hline
    
#----------------------------------------------------------------------
def cv2_test():
    """TEST cv2_minRectAxes"""
    im=np.zeros([480,640,3],np.uint8)
    xx=np.zeros([4,2],np.int0)
    for i in xrange(4): xx[i,:] = np.int0((random()*640,random()*480))
    #print xx
    cv2.drawContours(im,[xx],-1,cv2_white,-1)
    x = cv2.minAreaRect(xx)
    x = np.int0(cv2.cv.BoxPoints(x))
    cv2.drawContours(im,[x],-1,cv2_yellow,2)
    (w,h),wl,hl = cv2_minRectAxes(x)
    #print x
    #print (w,h),wl,hl
    cv2.line(im,wl[0],wl[1],cv2_yellow,2)
    cv2.line(im,hl[0],hl[1],cv2_purple,2)
    cv2.namedWindow('im')
    cv2.imshow('im',im)
    print "press any key to quit"
    cv2.waitKey()
    cv2.destroyAllWindows()
#----------------------------------------------------------------------
