import subprocess
import os
import glob

from code.config import env_paths

_ENV_PATHS = env_paths()

_TEA_HOME = os.path.join(*([os.path.dirname(os.path.abspath(__file__))]+[".."]*4))

_dict_entry = lambda morpho_line: {"token": morpho_line[0],
                                  "pos": morpho_line[1],
                                  "morphology": morpho_line[2:-1],
                                  "chunk": morpho_line[-1]}

_new_sentence = lambda l: l[0:1] == ''
_comment      = lambda l: l[0:1] == '#'

def process(text, base_filename=None, overwrite=False):
    """Perform morphological analysis on a text doc.

       text: body of text document
       base_filename: base name of time ml docuemnt, ex: APW19980219.0476 from APW19980219.0476.tml.TE3input
       overwrite: overwrite existing base_filename. Set to false to load existing annotation, since morphopro takes a long time to load.
    """

    # TODO: make direct api calls and load morphopro into memory.

    _DEFAULT_OUTPUT_DIR = os.path.join(_TEA_HOME, "morpho_output")

    dest_path = None
    morpho_output = None

    if base_filename is None:
        dest_path = os.path.join(_DEFAULT_OUTPUT_DIR, "tmp.morpho")
    else:
        dest_path = os.path.join(_DEFAULT_OUTPUT_DIR, base_filename + ".morpho")

    processed_files = [os.path.basename(f_path) for f_path in glob.glob(os.path.join(_DEFAULT_OUTPUT_DIR,"*"))]

    if overwrite is False and base_filename is not None and base_filename + ".morpho" in processed_files:
        print "stashed morpho processed file found"
        # return contents of existing file
        morpho_output = open(dest_path,"rb").read()
    else:
        print "morphopro processing file: ", base_filename
        morpho = subprocess.Popen(["bash",
                                   os.path.join(_ENV_PATHS["MORPHO_DIR_PATH"], "textpro.sh"), # script we're running.
                                   "-l", # select language.
                                   "eng",
                                   "-c", # select what we want to do to text.
                                   "token+pos+full_morpho+chunk"],
                                   stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE)

        morpho_output, _ = morpho.communicate(text)

        # save parsed output to file
        with open(dest_path,"wb") as f:
            f.write(morpho_output)

    output = []

    # intialize
    sentence = []
    output.append(sentence)

    for line in morpho_output.strip('\n').split('\n'):
        # start of new sentence
        if _new_sentence(line):
            sentence = []
            output.append(sentence)
        elif _comment(line):
            continue
        else:
            # take advantage of python referencing
            sentence.append(_dict_entry(line.split('\t')))

    return output
