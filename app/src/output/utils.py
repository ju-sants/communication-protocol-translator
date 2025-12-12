
def normalize_dev_id(dev_id: str) -> str:
    if "803612c9" in dev_id: dev_id = dev_id.replace("803612c9", "")
    if "803912c9" in dev_id: dev_id = dev_id.replace("803912c9", "")
    if "00000002" in dev_id: dev_id = dev_id.replace("00000002", "")
    if "80360001" in dev_id: dev_id = dev_id.replace("80360001", "")
    
    dev_id = dev_id.zfill(20)
    
    return ''.join(filter(str.isdigit, dev_id))

def get_output_dev_id(dev_id: str, output_protocol: str) -> str:
    dev_id = normalize_dev_id(dev_id)
    output_dev_id = None

    if output_protocol.lower() == "suntech4g":
        output_dev_id = dev_id[-10:]
    if output_protocol.lower() == "gt06":
        output_dev_id = dev_id[-15:]

    return output_dev_id
