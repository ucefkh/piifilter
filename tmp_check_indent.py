with open("/home/ucefkh/projects/privacy-proxy-ai/plugins/detector-regex/src/piifilter_detector_regex/detector.py") as f:
    lines = f.readlines()
for i in range(775, min(845, len(lines))):
    print("{:4d}|{:s}".format(i+1, lines[i].rstrip()))