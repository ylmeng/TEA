import os
import itertools
import sys
import re
import copy

from string import whitespace
from Note import Note

from utilities.timeml_utilities import annotate_root
from utilities.timeml_utilities import annotate_text_element
from utilities.timeml_utilities import get_doctime_timex
from utilities.timeml_utilities import get_make_instances
from utilities.timeml_utilities import get_stripped_root
from utilities.timeml_utilities import get_tagged_entities
from utilities.timeml_utilities import get_text
from utilities.timeml_utilities import get_text_element
from utilities.timeml_utilities import get_text_element_from_root
from utilities.timeml_utilities import get_text_with_taggings
from utilities.timeml_utilities import get_tlinks
from utilities.timeml_utilities import set_text_element

from utilities.xml_utilities import get_raw_text
from utilities.xml_utilities import get_root
from utilities.xml_utilities import write_root_to_file

# from utilities.time_norm import get_normalized_time_expressions
from utilities.pre_processing import pre_processing

class TimeNote(Note):

    def __init__(self, timeml_note_path, annotated_timeml_path=None, verbose=False):

        if verbose: print "called TimeNote constructor"

        _Note = Note.__init__(self, timeml_note_path, annotated_timeml_path)

        # get body of document
        data = get_text(timeml_note_path)

        # original text body of timeml doc
        self.original_text = data

        # send body of document to NewsReader pipeline.
        tokenized_text, token_to_offset, sentence_features, dependency_paths, id_to_tok = pre_processing.pre_process(data, timeml_note_path)

        # {sentence_num: [{token},...], ...}
        self.pre_processed_text = tokenized_text

        # contains the char based offsets generated by tokenizer, used for asserting char offsets are correct
        # {'token':[(start, end),...],...}
        self.token_to_offset = token_to_offset

        # contains sentence level information extracted by newsreader
        self.sentence_features = sentence_features

        # dependency paths for sentences in the document
        self.dependency_paths = dependency_paths

        # map token ids to tokens within self.tokenized_text
        # {'wid':'token'}
        self.id_to_tok = id_to_tok

        self.discourse_connectives = {}

        self.iob_labels = []

        """
        print "\n\nself.original_text:\n\n"
        print self.original_text
        print "\n\n"

        print "self.pre_processed_text:\n\n"
        print tokenized_text
        print "\n\n"

        print "self.token_to_offset:\n\n"
        print self.token_to_offset
        print "\n\n"

        print "self.sentence_features:\n\n"
        print self.sentence_features
        print "\n\n"
        """

        self.tlinks = []

        if self.annotated_note_path is not None:

            self.get_tlinked_entities()

            # will store labels in self.iob_labels
            self.get_labels()

    def get_sentence_features(self):
        return self.sentence_features

    def get_tokenized_text(self):
        return self.pre_processed_text

    def get_discourse_connectives(self):
        return self.discourse_connectives

    def add_discourse_connectives(self, connectives):
        self.discourse_connectives.update(connectives)

    def get_timex_labels(self):
        return self.filter_label_by_type('TIMEX3')

    def get_event_labels(self):

        labels = self.filter_label_by_type("EVENT")

        for line in labels:
            for label in line:
                if label["entity_type"] != "EVENT":
                    label['entity_label'] = 'O'
                else:
                    label['entity_label'] = "EVENT"

        return labels

    def get_event_class_labels(self):
         return self.filter_label_by_type('EVENT')

    def filter_label_by_type(self, entity_type):
        assert entity_type in ['EVENT', 'TIMEX3']

        labels = copy.deepcopy(self.get_labels())

        for line in labels:
            for label in line:

                if label["entity_type"] != entity_type:
                    label['entity_label'] = 'O'

        return labels

    def set_tlinked_entities(self, timexLabels, eventClassLabels):
        """
            Set the tlink entities given the taggings from classifiers.
            This is used during prediction prior to feature extraction of tlink pairings.
            NOTE: this function will modify the dictionaries within timexLabels to correct I_ before B_ taggings.
        """

        # there should be no tlinks if this method is called.
        assert len(self.tlinks) == 0

        entity_pairs = self.get_entity_pairs()

        relation_count = 0

        pairs_to_link = []
        tlink_ids = []

        id_chunk_map, event_ids, timex_ids, sentence_chunks = self.get_id_chunk_map()

        # create the pair representation.
        for pair in entity_pairs:

            src_id = pair[0]
            target_id = pair[1][1]

            pair = {"src_entity":id_chunk_map[src_id],
                    "src_id":src_id,
                    "target_id":target_id,
                    "target_entity":id_chunk_map[target_id],
                    "rel_type":'None',
                    # no links!
                    "tlink_id":None}

            pairs_to_link.append(pair)

        self.tlinks = pairs_to_link

        return

    def get_tlinked_entities(self):

        t_links = None

        if len(self.tlinks) > 0:
            return self.tlinks
        elif self.annotated_note_path is not None:
            t_links = get_tlinks(self.annotated_note_path)
            make_instances = get_make_instances(self.annotated_note_path)
        else:
            print "no annotated timeml note to get tlinks from returning empty list..."
            self.tlinks = []
            return self.tlinks

        temporal_relations = {}

        eiid_to_eid = {}

        for instance in make_instances:
            eiid_to_eid[instance.attrib["eiid"]] = instance.attrib["eventID"]

        gold_tlink_pairs = []

        # TODO: figure out how to handle the problem where a token occurs in two different make instances.
        for t in t_links:

            link = {}

            # source
            if "eventInstanceID" in t.attrib:
                src_id = eiid_to_eid[t.attrib["eventInstanceID"]]
            else:
                src_id = t.attrib["timeID"]

            # target
            if "relatedToEventInstance" in t.attrib:
                target_id = eiid_to_eid[t.attrib["relatedToEventInstance"]]
            else:
                target_id = t.attrib["relatedToTime"]

            tmp_dict = {"target_id":target_id, "rel_type":t.attrib["relType"], "lid":t.attrib["lid"]}

            gold_tlink_pairs.append((src_id, target_id))

            if src_id in temporal_relations:
                # this would mean the same src id will map to same target with different relation type.
                # not possible.
                assert tmp_dict not in temporal_relations[src_id]
                temporal_relations[src_id].append(tmp_dict)
            else:
                temporal_relations[src_id] = [tmp_dict]

        assert( len(gold_tlink_pairs) == len(t_links) ), "{} != {}".format(len(gold_tlink_pairs) , len(t_links))

        entity_pairs = self.get_entity_pairs()

        relation_count = 0

        pairs_to_link = []
        tlink_ids = []

        #print "entity paurs:"
        #print entity_pairs

        #print "sentence_chunks: "
        #print sentence_chunks

        id_chunk_map, event_ids, timex_ids, sentence_chunks = self.get_id_chunk_map()

        for pair in entity_pairs:

            src_id = pair[0]
            target_id = pair[1][1]

            # print "id_chunk_map: "
            # print id_chunk_map
            # print "src_id: "
            # print src_id
            # print "target_id: "
            # print target_id

            pair = {"src_entity":id_chunk_map[src_id],
                    "src_id":src_id,
                    "target_id":target_id,
                    "target_entity":id_chunk_map[target_id],
                    "rel_type":'None',
                    "tlink_id":None}


            if src_id in temporal_relations:

                # relation_found = False

                for target_entity in temporal_relations[src_id]:

                    if target_id == target_entity["target_id"]:

                        relation_count += 1

                        # need to assign relation to each pairing if there exists one otherwise set 'none'
                        pair["rel_type"] = target_entity["rel_type"]

                        # need to simplify tlinks

                        if pair["rel_type"] in ["IDENTITY", "DURING"]:
                            pair["rel_type"] = "SIMULTANEOUS"
                        elif pair["rel_type"] == "IBEFORE":
                            pair["rel_type"] = "BEFORE"
                        elif pair["rel_type"] == "IAFTER":
                            pair["rel_type"] = "AFTER"
                        elif pair["rel_type"] == "INCLUDES":
                            pair["rel_type"] = "IS_INCLUDED"
                        elif pair["rel_type"] == "BEGINS":
                            pair["rel_type"] = "BEGUN_BY"
                        elif pair["rel_type"] == "ENDS":
                            pair["rel_type"] = "ENDED_BY"
                        elif pair["rel_type"] not in [
                                                    "BEGUN_BY",
                                                    "IS_INCLUDED",
                                                    "AFTER",
                                                    "ENDED_BY",
                                                    "SIMULTANEOUS",
                                                    "DURING",
                                                    "IDENTITY",
                                                    "BEFORE"
                                                 ]:
                            print "rel_type: ", pair["rel_type"]
                            exit("unknown rel_type")

                        pair["tlink_id"] = target_entity["lid"]

                        tlink_ids.append(target_entity["lid"])

                        # done
                        break

            # no link at all
            pairs_to_link.append(pair)

        # TODO: if this fails just remove the assertion...
        # make sure we don't miss any tlinks
        #assert relation_count == len(t_links), "{} != {}".format(relation_count, len(t_links))

        self.tlinks = pairs_to_link

        return self.tlinks

    def get_entity_pairs(self):

        id_chunk_map, event_ids, timex_ids, sentence_chunks = self.get_id_chunk_map()

        doctime = get_doctime_timex(self.note_path)
        doctime_id = doctime.attrib["tid"]

        entity_pairs = []

        # TODO: make more efficient...
        for sentence_num in sentence_chunks:
            for i, entity in enumerate(sentence_chunks[sentence_num]):
                entity_id   = entity[1]
                entity_type = entity[0]

                if entity_type == "EVENT":
                    entity_pairs += list(itertools.product([entity_id], sentence_chunks[sentence_num][i+1:]))
                    entity_pairs.append((entity_id, ("TIMEX", doctime_id)))
                else:
                    events = map(lambda event: event[1], filter(lambda entity: entity[0] == "EVENT", sentence_chunks[sentence_num][i+1:]))
                    entity_pairs += list(itertools.product(events,
                                                           [("TIMEX", entity_id)]))

                    #if entity_id is None:
                        #print "NONE TIMEX ID????"
                        #print  entity

            if sentence_num + 1 in sentence_chunks:

                # get events of sentence
                event_ids = filter(lambda entity: entity[0] == "EVENT", sentence_chunks[sentence_num])
                main_events = filter(lambda event_id: True in [token["is_main_verb"] for token in id_chunk_map[event_id[1]]], event_ids)
                main_events = map(lambda event: event[1], main_events)

                # get adjacent sentence events and filter the main events
                adj_event_ids = filter(lambda entity: entity[0] == "EVENT", sentence_chunks[sentence_num+1])
                adj_main_events = filter(lambda event_id: True in [token["is_main_verb"] for token in id_chunk_map[event_id[1]]], adj_event_ids)

                entity_pairs += list(itertools.product(main_events, adj_main_events))

        return entity_pairs

    def get_id_chunk_map(self):

        event_ids = set()
        timex_ids = set()

        chunks = []
        chunk = []

        id_chunk = []
        id_chunks = []

        start_entity_id = None

        id_chunk_map = {}

        B_seen = False

        sentence_chunks = {}

        # get tagged entities and group into a list
        for sentence_num, labels in zip(self.pre_processed_text, self.get_labels()):

            sentence_chunks[sentence_num] = []

            for token, label in zip(self.pre_processed_text[sentence_num], labels):

                if label["entity_type"] == "EVENT":

                    _chunk = [token]
                    chunks.append(_chunk)

                    event_ids.add(label["entity_id"])

                    id_chunks.append([label["entity_id"]])

                    # TODO: gonna drop multi span events...
                    assert label["entity_id"] not in id_chunk_map

                    id_chunk_map[label["entity_id"]] = _chunk

                    sentence_chunks[sentence_num].append(("EVENT", label["entity_id"]))

                # start of timex
                elif re.search('^B_', label["entity_label"]):

                    timex_ids.add(label["entity_id"])

                    if len(chunk) != 0:
                        chunks.append(chunk)
                        id_chunks.append(id_chunk)

                        assert start_entity_id not in id_chunk_map

                        #print "TIMEX: adding to id_chunk _map"
                        #print "\t", label

                        id_chunk_map[start_entity_id] = chunk

                        #if start_entity_id is None:
                        #    print "start_entity_id is NONE"
                        #    print label

                        sentence_chunks[sentence_num].append(("TIMEX", start_entity_id))

                        chunk = [token]
                        id_chunk = [label["entity_id"]]


                    else:
                        chunk.append(token)
                        id_chunk.append(label["entity_id"])

                    start_entity_id = label["entity_id"]

                    B_seen = True

                # in timex chunk
                elif re.search('^I_', label["entity_label"]):

                    assert label["entity_id"] == start_entity_id, "{} != {}, B_seen is {}".format(label["entity_id"], start_entity_id, B_seen)

                    chunk.append(token)
                    id_chunk.append(label["entity_id"])

                else:
                    pass

            if len(chunk) != 0:
                chunks.append(chunk)
                assert len(id_chunk) == len(chunk)
                id_chunks.append(id_chunk)

                assert start_entity_id not in id_chunk_map
                id_chunk_map[start_entity_id] = chunk

                sentence_chunks[sentence_num].append(("TIMEX", start_entity_id))

            chunk = []
            id_chunk = []

        assert len(event_ids.union(timex_ids)) == len(id_chunks), "{} != {}".format(len(event_ids.union(timex_ids)), len(id_chunks))
        assert len(id_chunk_map.keys()) == len(event_ids.union(timex_ids)), "{} != {}".format(len(id_chunk_map.keys()), len(event_ids.union(timex_ids)))

        # TODO: need to add features for doctime. there aren't any.
        # add doc time. this is a timex.
        doctime = get_doctime_timex(self.note_path)
        doctime_id = doctime.attrib["tid"]
        doctime_dict = {}

        # create dict representation of doctime timex
        for attrib in doctime.attrib:
            doctime_dict[attrib] = doctime.attrib[attrib]

        id_chunk_map[doctime_id] = [doctime_dict]
        timex_ids.add(doctime_id)


        return id_chunk_map, event_ids, timex_ids, sentence_chunks

    def get_labels(self):

        if self.annotated_note_path is not None and self.iob_labels == []:

            # don't want to modify original
            pre_processed_text = copy.deepcopy(self.pre_processed_text)

            # need to create a list of tokens
            iob_labels = []

            tagged_entities = get_tagged_entities(self.annotated_note_path)
            _tagged_entities = copy.deepcopy(tagged_entities)

            raw_text = get_text(self.note_path)
            labeled_text = get_text_with_taggings(self.annotated_note_path)

            # lots of checks!
            for char in ['\n'] + list(whitespace):
                raw_text     = raw_text.strip(char)
                labeled_text = labeled_text.strip(char)

            raw_text     = re.sub(r"``", r"''", raw_text)
            labeled_text = re.sub(r'"', r"'", labeled_text)

            raw_text = re.sub("<TEXT>\n+", "", raw_text)
            raw_text = re.sub("\n+</TEXT>", "", raw_text)

            labeled_text = re.sub("<TEXT>\n+", "", labeled_text)
            labeled_text = re.sub("\n+</TEXT>", "", labeled_text)

            raw_index = 0
            labeled_index = 0

            raw_char_offset = 0
            labeled_char_offset = 0

            # should we count?
            count_raw = True
            count_labeled = True

            text1 = ""
            text2 = ""

            start_count = 0
            end_count = 0

            offsets = {}

            tagged_element = None

            # need to get char based offset for each tagging within annotated timeml doc.
            while raw_index < len(raw_text) or labeled_index < len(labeled_text):

                if raw_index < len(raw_text):
                    if count_raw is True:
                        raw_char_offset += 1
                        text1 += raw_text[raw_index]
                    raw_index += 1

                if labeled_index < len(labeled_text):

                    # TODO: change this to be an re match.
                    if labeled_text[labeled_index:labeled_index+1] == '<' and labeled_text[labeled_index:labeled_index+2] != '</':

                        tagged_element = tagged_entities.pop(0)

                        count_labeled = False
                        start_count += 1

                    elif labeled_text[labeled_index:labeled_index+2] == '</':
                        count_labeled = False
                        start_count += 1

                    if labeled_text[labeled_index:labeled_index+1] == ">":

                        if tagged_element != None:

                            start = labeled_char_offset
                            end   = labeled_char_offset+len(tagged_element.text) - 1

                            # spans should be unique?
                            offsets[(start, end)] = {"tagged_xml_element":tagged_element, "text":tagged_element.text}

                            # ensure the text at the offset is correct
                            assert raw_text[start:end + 1] == tagged_element.text, "\'{}\' != \'{}\'".format( raw_text[start:end + 1], tagged_element.text)
                            tagged_element = None

                        end_count += 1
                        count_labeled = True

                        labeled_index += 1
                        continue

                    if count_labeled is True:
                        labeled_char_offset += 1
                        text2 += labeled_text[labeled_index]

                    labeled_index += 1

            assert text1 == text2, "{} != {}".format(text1, text2)
            assert start_count == end_count, "{} != {}".format(start_count, end_count)
            assert raw_index == len(raw_text) and labeled_index == len(labeled_text)
            assert raw_char_offset == labeled_char_offset
            assert len(tagged_entities) == 0
            assert tagged_element is None
            assert len(offsets) == len(_tagged_entities)

            for sentence_num in sorted(pre_processed_text.keys()):

                # list of dicts
                sentence = pre_processed_text[sentence_num]

                # iobs in a sentence
                iobs_sentence = []

                # need to assign the iob labels by token index
                for token in sentence:


                    # set proper iob label to token
                    iob_label, entity_type, entity_id = TimeNote.get_label(token, offsets)

                    if iob_label is not 'O':
                        assert entity_id is not None
                        assert entity_type in ['EVENT', 'TIMEX3']
                    else:
                        assert entity_id is None
                        assert entity_type is None



                    #if token["token"] == "expects":
                    #    print "Found expects"
                    #    print "iob_label: ", iob_label
                    #    print "entity_type: ", entity_type
                    #    print "entity_id: ", entity_id
                    #    print
                    #    sys.exit("done")

                    iobs_sentence.append({'entity_label':iob_label,
                                          'entity_type':entity_type,
                                          'entity_id':entity_id})

                iob_labels.append(iobs_sentence)

            self.iob_labels = iob_labels

        return self.iob_labels

    def get_tokens(self):

        tokens = []

        for line in self.pre_processed_text:

            for token in self.pre_processed_text[line]:

                tokens.append(token)

        return tokens

    def set_iob_labels(self, iob_labels):

        # don't over write existing labels.
        assert len(self.iob_labels) == 0

        self.iob_labels = iob_labels

    def get_tlink_ids(self):

        tlink_ids = []

        for tlink in self.tlinks:

            tlink_ids.append(tlink["tlink_id"])

        return tlink_ids

    def get_tlink_labels(self):
        """ return the labels of each tlink from annotated doc """

        tlink_labels = []

        for tlink in self.tlinks:

            tlink_labels.append(tlink["rel_type"])

        return tlink_labels

    def get_tlink_id_pairs(self):

        """ returns the id pairs of two entities joined together """

        tlink_id_pairs = []

        for tlink in self.tlinks:

            tlink_id_pairs.append((tlink["src_id"], tlink["target_id"]))

        return tlink_id_pairs

    def get_token_char_offsets(self):

        """ returns the char based offsets of token.

        for each token within self.pre_processed_text iterate through list of dicts
        and for each value mapped to the key 'start_offset' and 'end_offset' create a
        list of 1-1 mappings

        Returns:
            A flat list of offsets of the token within self.pre_processed_text:

                [(0,43),...]
        """

        offsets = []

        for line_num in self.pre_processed_text:
            for token in self.pre_processed_text[line_num]:
                offsets.append((token["char_start_offset"], token["char_end_offset"]))

        return offsets

    def get_tokens_from_ids(self, ids):
        ''' returns the token associated with a specific id'''
        tokens = []
        for _id in ids:
            # ensuring id prefix value is correct.
            # TODO: adjust TimeNote to consistently use t# or w# format
            tokens.append(self.id_to_tok['w' + _id[1:]]["token"])
        return tokens

    def write(self, timexEventLabels, tlinkLabels, idPairs, offsets, tokens, output_path):
        '''
        Note::write()

        Purpose: add annotations this notes tml file and write new xml tree to a .tml file in the output folder.

        params:
            timexEventLabels: list of dictionaries of labels for timex and events.
            tlinkLabels: list labels for tlink relations
            idPairs: list of pairs of eid or tid that have a one to one correspondance with the tlinkLabels
            offsets: list of offsets tuples used to locate events and timexes specified by the label lists. Have one to one correspondance with both lists of labels.
            tokens: tokens in the note (used for tense)
            output_path: directory to write the file to
        '''
        # TODO: create output directory if it does not exist
        root = get_stripped_root(self.note_path)
        length = len(offsets)
        doc_time = get_doctime_timex(self.note_path).attrib["value"]

        # hack so events are detected in next for loop.
        for label in timexEventLabels:
            if label["entity_label"][0:2] not in ["B_","I_","O"] or label["entity_label"] in ["I_STATE", "I_ACTION"]:
                label["entity_label"] = "B_" + label["entity_label"]

        # start at back of document to preserve offsets until they are used
        for i in range(1, length+1):
            index = length - i

            if timexEventLabels[index]["entity_label"][0:2] == "B_":
                start = offsets[index][0]
                end = offsets[index][1]
                entity_tokens = tokens[index]["token"]

                #grab any IN tokens and add them to the tag text
                for j in range (1, i):

                    if(timexEventLabels[index + j]["entity_label"][0:2] == "I_"):
                        end = offsets[index + j][1]
                        entity_tokens += ' ' + tokens[index + j]["token"]
                    else:
                        break

                if timexEventLabels[index]["entity_type"] == "TIMEX3":
                    # get the time norm value of the time expression
                    # timex_value = get_normalized_time_expressions(doc_time, [entity_tokens])
                    timex_value = ''
                    # if no value was returned, set the expression to an empty string
                    # TODO: check if TimeML has a specific default value we should use here
                    if len(timex_value) != 0:
                        timex_value = timex_value[0]
                    else:
                        timex_value = ''

                   # if None in [start, end,  timexEventLabels[index]["entity_id"], timexEventLabels[index]["entity_label"][2:], timex_value]:
                   #     print "FOUND NoNE"
                   #     print [start, end,  timexEventLabels[index]["entity_id"], timexEventLabels[index]["entity_label"][2:], timex_value]
        #          #      exit()
                   # else:
                   #     print "NONE NONE"
                   #     print [start, end,  timexEventLabels[index]["entity_id"], timexEventLabels[index]["entity_label"][2:], timex_value]


                    annotated_text = annotate_text_element(root, "TIMEX3", start, end, {"tid": timexEventLabels[index]["entity_id"], "type":timexEventLabels[index]["entity_label"][2:], "value":timex_value})
                else:
                    annotated_text = annotate_text_element(root, "EVENT", start, end, {"eid": timexEventLabels[index]["entity_id"], "class":timexEventLabels[index]["entity_label"][2:]})
                    #if None in [start, end,  timexEventLabels[index]["entity_id"], timexEventLabels[index]["entity_label"][2:], timex_value]:
                    #    print "FOUND NoNE"
                    #    print [start, end,  timexEventLabels[index]["entity_id"], timexEventLabels[index]["entity_label"][2:], timex_value]
        #                exit()
                    #else:
                    #    print "NONE NONE"
                    #    print [start, end,  timexEventLabels[index]["entity_id"], timexEventLabels[index]["entity_label"][2:], timex_value]

                set_text_element(root, annotated_text)

        # make event instances
        eventDict = {}
        for i, timexEventLabel in enumerate(timexEventLabels):

            token = tokens[i]

            pos = None

            # pos
           # if token["pos_tag"] == "IN":
           #     pos = "PREPOSITION"
           # elif token["pos_tag"] in ["VB", "VBD","VBG", "VBN", "VBP", "VBZ", "RB", "RBR", "RBS"]:
           #     pos = "VERB"
           # elif token["pos_tag"] in ["NN", "NNS", "NNP", "NNPS", "PRP", "PRP$"]:
           #     pos = "NOUN"
           # elif token["pos_tag"] in ["JJ", "JJR", "JJS"]:
           #     pos = "ADJECTIVE"
           # else:
           #     pos = "OTHER"

            if timexEventLabel["entity_type"] == "EVENT":
                root = annotate_root(root, "MAKEINSTANCE", {"eventID": timexEventLabel["entity_id"], "eiid": "ei" + str(i), "tense":"NONE", "pos":"NONE"})
                eventDict[timexEventLabel["entity_id"]] = "ei" + str(i)

        # add tlinks
        for i, tlinkLabel in enumerate(tlinkLabels):

            if tlinkLabel == "None":
                continue

            annotations = {"lid": "l" + str(i), "relType": tlinkLabel}

            firstID = idPairs[i][0]
            secondID = idPairs[i][1]

            if firstID[0] == "e":
                annotations["eventInstanceID"] = eventDict[firstID]

            if firstID[0] == "t":
                annotations["timeID"] = firstID

            if secondID[0] == "e":
                annotations["relatedToEventInstance"] = eventDict[secondID]

            if secondID[0] == "t":
                annotations["relatedToTime"] = secondID

            root = annotate_root(root, "TLINK", annotations)

        note_path = os.path.join(output_path, self.note_path.split('/')[-1] + ".tml")

        print "root: ", root
        print "note_path: ", note_path

        write_root_to_file(root, note_path)

    @staticmethod
    def get_label(token, offsets):

        # NOTE: never call this directly. input is tested within _read
        tok_span = (token["char_start_offset"], token["char_end_offset"])

        label = 'O'
        entity_id = None
        entity_type = None

        for span in offsets:

            if offsets[span]["tagged_xml_element"].tag not in ["EVENT", "TIMEX3"]:
                continue

            if TimeNote.same_start_offset(span, tok_span):

                labeled_entity = offsets[span]["tagged_xml_element"]

                if 'class' in labeled_entity.attrib:
                    label = 'B_' + labeled_entity.attrib["class"]
                elif 'type' in labeled_entity.attrib:
                    label = 'B_' + labeled_entity.attrib["type"]

                if 'eid' in labeled_entity.attrib:
                    entity_id = labeled_entity.attrib["eid"]
                else:
                    entity_id = labeled_entity.attrib["tid"]

                entity_type = labeled_entity.tag

                break

            elif TimeNote.subsumes(span, tok_span):

                labeled_entity = offsets[span]["tagged_xml_element"]

                if 'class' in labeled_entity.attrib:
                    label = 'I_' + labeled_entity.attrib["class"]
                else:
                    label = 'I_' + labeled_entity.attrib["type"]

                if 'eid' in labeled_entity.attrib:
                    entity_id = labeled_entity.attrib["eid"]
                else:
                    entity_id = labeled_entity.attrib["tid"]

                entity_type = labeled_entity.tag

                break

       # if token["token"] == "expects":

       #     print
       #     print "Token span: ", tok_span
       #     print "Label found: ", label
       #     print

       #     sys.exit("found it")

        if entity_type == "EVENT":
            # don't need iob tagging just what the type is.
            # multi token events are very rare.
            label = label[2:]

        return label, entity_type, entity_id

    @staticmethod
    def same_start_offset(span1, span2):
        """
        doees span1 share the same start offset?
        """
        return span1[0] == span2[0]

    @staticmethod
    def subsumes(span1, span2):
        """
        does span1 subsume span2?
        """
        return span1[0] < span2[0] and span2[1] <= span1[1]


def __unit_tests():

    """ basic assertions to ensure output correctness """

    t =  TimeNote("APW19980219.0476.tml.TE3input", "APW19980219.0476.tml")

    for label in t.get_timex_iob_labels():
        for token in label:

            if token['entity_type'] == 'TIMEX3':
                assert token['entity_label'] != 'O'
            else:
                assert token['entity_label'] == 'O'

    for label in t.get_event_iob_labels():
        for token in label:

            if token['entity_type'] == 'EVENT':
                assert token['entity_label'] != 'O'
            else:
                assert token['entity_label'] == 'O'

    """
    number_of_tlinks = len(t.get_tlink_features())
    assert number_of_tlinks != 0
    assert len(t.get_tlink_id_pairs()) == number_of_tlinks, "{} != {}".format(len(t.get_tlink_id_pairs()), number_of_tlinks)
    assert len(t.get_tlink_labels()) == number_of_tlinks
    assert len(t.get_tlink_ids()) == number_of_tlinks
    #prin t.get_token_char_offsets()
    """

    t.get_tlink_features()

#    print t.get_iob_features()

#    print t.get_tlinked_entities()

#    print t.get_tlink_labels()

if __name__ == "__main__":

    __unit_tests()

    print "nothing to do"




