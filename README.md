# Temporal Entity Annotator (TEA)
## Credentials

The code in this repository was used in the following publication:  Y. Meng, A. Rumshisky, A. Romanov.  Temporal Information Extraction for Question Answering Using Syntactic Dependencies in an LSTM-based Architecture. EMNLP 2017. http://aclweb.org/anthology/D17-1093

A (very simple) webpage of this project can be found here http://www.cs.uml.edu/~ymeng/projects/temporalIE/TEA.html
Yuanliang Meng (ylmeng) developed the code in collaboration with Anna Rumshisky and Alexey Romanov. Kevin Wacome (kwaco) and Connor Cooper (c-cooper) were early contributors, including the modules for preprocessing, and some preliminary network models. You may contact ylmeng for any issues.

Copyright (c) 2017 UMass Lowell - All Rights Reserved

You may use, distribute and modify this code under the terms of the Apache 2.0 license. See https://www.apache.org/licenses/LICENSE-2.0 for details

## How to install:

    1. Download the latest release from:

        https://github.com/text-machine-lab/TEA/releases

    2. Also download the NewsReader.tar file from the release.

    3. Uncompress source code.

        A folder called Temporal-Entity-Annotator-TEA-VERSION should be created

    4. Place NewsReader.tar within the extracted folder.

    5. Change current working directory to be the extracted folder.

    6. Execute the bash script install_dependencies.sh
    Make sure every line in install_dependencies.sh work through. You will need mvn and javac.
    Set JAVA_HOME properly for javac to work.

External Dependencies:

    - maven 3
    - java 1.7 or higher
    - python 2.7 (does not work with python 3+)
    - scala 2.11.7 or higher
    - python modules
      - numpy
      - scipy
      - scikit-learn (sklearn)
      - keras
      - gensim
      - h5py
      - nltk
      - py4j
      - CorefGraph
            - how to install CorefGraph:
                $  pip install --allow-all-external --process-dependency-links hg+https://bitbucket.org/Josu/corefgraph#egg=corefgraph

                    - corefgraph needs the following resources:

                        $ hg clone https://bitbucket.org/Josu/corefgraph
                        $ cp corefgraph/corefgraph /usr/local/lib/python2.7/dist-packages/

Environment Variables:

    1. There are two environment variables that need to be defined for the system to work:
        - TEA_PATH, should be set to where you install this package.

        - PY4J_DIR_PATH, should be set to the folder /share/py4j or /share/local/py4j, created when installing py4j.
            - It should contain the contain the file py4j0.8.2.1.jar
          create config.txt in your TEA path. Add this line to the file (change the path to yours):
           PY4J_DIR_PATH /share/local/py4j

Tensorflow and Theano:
    
    We tested our model on Tensorflow 1.2.0 and Theano 0.9.0-dev. You should be able to use either one. Our keras version is 2.0.4.

## Data Sets:

Uncompress data.tar.gz to get training data, validation data and test data. The folder test_tagged contains data files with EVENT tags and TIMEX3 tags, and you can use them to predict TLINKs. The folder test_raw contains data files without any EVENT or TIMEX3 tag. If you want to use data there, you will need to generate the tags somewhere in the pipeline.

You can use anyway you like to do evaluation. However we followed the QA evaluation from SemEval-2015 Task 5. You can download the QA toolkits for validation data and test data http://alt.qcri.org/semeval2015/task5/index.php?id=data-and-tools
We noticed some errors in the QA toolkit. Please refer to our paper for more details.

## How to use:
### Generate TIMEX3 tags
    
The folder test_tagged contains files with tags already. However, you can create your own tags from raw text too, as long as the format is compatible. We used the Heideltime package for this purpose. More information can be found here: https://github.com/HeidelTime/heideltime

### Generate EVENT tags
    
The folder test_tagged contains files with tags already. However, you can create your own tags from raw text too, as long as the format is compatible. If you like, the file event_network.py can be used to train a model to tag events. Use predict_event.py to write event tags after training.

### Train TLINK models

There are three trainable models: intra-sentence, cross-sentence and DCT (document creation time) model. Please read our paper for details. A example of training an intra-sentence model:

    $python train_network.py train/ model_destination/intra/ newsreader_annotations/ --val_dir val/ --pair_type intra --nolink 0.1
    
When you run a training script for the first time, the process will be slow because some note files will be created and saved in your directory for newsreader annotations. These files will be reused in the future if you train again, so the speed will be much faster. A quick explanation of the arguments and parameters:
    
    -model_destination, argument specifying path to save the trained model.
    -newsreader_annotations, argument specifying path to save and/or load note files generated by newsreader.
    -val_dir, parameter specifying the validation data path.
    -pair_type, either intra, or cross or dct.
    -nolink, a float indicating the sampling ratio of nolink/positive_link.

In order to finish the task, you need to train all three models.

### Annotate TLINKs

After you trained all three models, you can run this command to annotate TLINKs from files with EVENT and TIMEX3 tags:

    $python predict_network.py test_tagged/news/ model_destination/intra/ model_destination/cross/ model_destination/dct/ output_dir/ newsreader_annotations/

Then the system will use trained model to predict pair-wise temporal relations and perform other techniques to create TLINKs, and annotate the files. You can find the final output in your output_dir.

### QA evaluation

Please download QA toolkits for val and test data here http://alt.qcri.org/semeval2015/task5/index.php?id=data-and-tools
There are minor errors in the toolkits and our paper expains them.


