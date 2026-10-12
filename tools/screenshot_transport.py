"""MPlusLogs 64x64 monochrome screenshot packet. No screenshots sent to a server."""
from PIL import Image

MAGIC=b"MPLG"


def checksum(data):
    result=0
    for byte in data:
        result=(result*31+byte)%65536
    return result


def encode_image(text,cell=6,origin=(24,24),size=(1024,768)):
    data=text.encode("utf-8")
    if len(data)>504:
        raise ValueError("Packet too large")
    packet=MAGIC+len(data).to_bytes(2,"big")+checksum(data).to_bytes(2,"big")+data
    packet=packet.ljust(512,b"\0")
    image=Image.new("RGB",size,"#777777")
    from PIL import ImageDraw
    draw=ImageDraw.Draw(image)
    ox,oy=origin
    draw.rectangle((ox-8,oy-8,ox+64*cell+7,oy+64*cell+7),fill="white")
    for bit in range(4096):
        value=(packet[bit//8]>>(7-bit%8))&1
        x,y=ox+(bit%64)*cell,oy+(bit//64)*cell
        draw.rectangle((x,y,x+cell-1,y+cell-1),fill="black" if value else "white")
    return image


def decode_at(image,x,y,cell):
    pixels=image.load()
    def bit(index):
        px=int(x+(index%64+.5)*cell)
        py=int(y+(index//64+.5)*cell)
        return int(pixels[px,py]<128)
    def byte(index):
        result=0
        for b in range(8):
            result=(result<<1)|bit(index*8+b)
        return result
    for i,expected in enumerate(MAGIC):
        if byte(i)!=expected:
            return None
    length=(byte(4)<<8)|byte(5)
    if not 1<=length<=504:
        return None
    expected=(byte(6)<<8)|byte(7)
    payload=bytes(byte(i) for i in range(8,8+length))
    if checksum(payload)!=expected:
        return None
    try:
        text=payload.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text if text.startswith("MPLS1\n") else None


def decode_image(image):
    image=image.convert("L")
    # IgnoreParentScale gives six physical pixels per cell. Other sizes allow
    # common render scaling; all candidates must pass magic, length and checksum.
    for cell in (6,5,7,4,8,3,9,10):
        for y in range(0,min(81,image.height-64*cell)):
            for x in range(0,min(81,image.width-64*cell)):
                text=decode_at(image,x,y,cell)
                if text:
                    return text
    return None


def decode_file(path):
    with Image.open(path) as image:
        if image.width>16000 or image.height>16000:
            raise ValueError("Screenshot too large")
        return decode_image(image)
