import os

PATH_REPERTOIRE = '/var/opt'

def parcourir():
    for root, dirs, files in os.walk(PATH_REPERTOIRE):
        for file in files:
            if file.endswith('.json.xz'):
                print(os.path.join(root, file))


if __name__ == '__main__':
    parcourir()
