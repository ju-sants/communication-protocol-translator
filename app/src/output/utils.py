
def normalize_dev_id(dev_id: str) -> str:
    if "803612c9" in dev_id: dev_id = dev_id.replace("803612c9", "")
    if "00000002" in dev_id: dev_id = dev_id.replace("00000002", "")
    
    dev_id = dev_id.zfill(15)
    
    return ''.join(filter(str.isdigit, dev_id))