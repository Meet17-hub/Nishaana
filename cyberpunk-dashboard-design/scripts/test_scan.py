import cv2 as cv
import numpy as np

def test():
    img = cv.imread('latest_warped.jpg')
    if img is None: 
        print('No image found at latest_warped.jpg')
        return
    h, w = img.shape[:2]
    # Crop to just the center to avoid finding 1000s of artifacts
    cx, cy = w//2, h//2
    # Assume target is in center 400x400
    gray = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
    blur = cv.GaussianBlur(gray, (5, 5), 0)
    
    thresh_white = cv.adaptiveThreshold(blur, 255, cv.ADAPTIVE_THRESH_GAUSSIAN_C, cv.THRESH_BINARY, 31, -10)
    cnts_w, _ = cv.findContours(thresh_white, cv.RETR_LIST, cv.CHAIN_APPROX_SIMPLE)
    
    thresh_dark = cv.adaptiveThreshold(blur, 255, cv.ADAPTIVE_THRESH_GAUSSIAN_C, cv.THRESH_BINARY_INV, 31, 10)
    cnts_d, _ = cv.findContours(thresh_dark, cv.RETR_LIST, cv.CHAIN_APPROX_SIMPLE)
    
    found = []
    for label, cnts in [('white', cnts_w)]:
        for cnt in cnts:
            area = cv.contourArea(cnt)
            if area < 30 or area > 1000: continue
            peri = cv.arcLength(cnt, True)
            if peri == 0: continue
            circ = 4 * np.pi * area / (peri * peri)
            if circ > 0.4:  
                r = np.sqrt(area / np.pi)
                M = cv.moments(cnt)
                if M['m00'] != 0:
                    found.append((M['m10']/M['m00'], M['m01']/M['m00'], r, circ, label))
    
    # Sort by size to see what's what
    found.sort(key=lambda x: x[2], reverse=True)
    print(f'Found {len(found)} candidates')
    for f in found[:20]: # show top 20
        print(f'X: {f[0]:.1f}, Y: {f[1]:.1f}, R: {f[2]:.1f}, Circ: {f[3]:.2f}, Type: {f[4]}')

test()
