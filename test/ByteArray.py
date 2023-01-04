import json
from io import StringIO, BytesIO


class BufferMessage:

    def __init__(self):
        self.__buffer = bytearray(8 * 1024)
        self.__len_courant = 0

    def get_bytes_io(self):
        return BytesIO(self.__buffer)

    def set_text(self, data):
        self.set_bytes(data.encode('utf-8'))

    def set_bytes(self, data):
        if len(data) > len(self.__buffer):
            raise ValueError('overflow')
        self.__len_courant = len(data)
        self.__buffer[:self.__len_courant] = data

    def clear(self):
        self.__len_courant = 0
        self.__buffer.clear()

    def __iter__(self):
        for i in range(0, self.__len_courant):
            return self.__buffer[i]

    def __len__(self):
        return self.__len_courant


def test2():
    buffer = BufferMessage()



def test1():
    ba = bytearray(64)
    print("BA : %s" % ba)

    dict_contenu = {'valeur': 'du contenu', 'int': 8}
    data = json.dumps(dict_contenu).encode('utf-8')
    ba[0:len(data)] = data
    data = None

    print("BA : %s (len: %d)" % (ba, len(ba)))

    #contenu_str = "allo".encode('utf-8')
    #print("Contenu str %s" % contenu_str)
    #len_str = len(contenu_str)
    #ba[0:len_str] = contenu_str

    #bio = BytesIO(ba)
    #reading = bio.read(len_str)
    #print("Reading : %s" % reading)


def main():
    test1()
    test2()


if __name__ == '__main__':
    main()
