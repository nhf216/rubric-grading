import sys
import os
import re
import readline
import collections
import subprocess

#Facilitate grading stuff with a rubric for lots of students
#Input 1: class list, with email addresses and optional groups
#Input 2: rubric, with optional categories
#Interface to toggle between students
#Interface to toggle between categories
#Categories can have enterable scores
#Interface to enter scores and comments
#Interface for excluding students
#Interface for general comments
#Writes things to text files (remembers row and name, in case rubric changes)
#Converts text files to .tex files
#Compiles .tex files into pdf
#Export grades to .csv, alphabetized
#Ability to change name of "TOTAL"
#Import comments from other students
#Interface for subject line of email
#Interface for body of email
#Interface for exceptional body of email
#Attach pdf to email
#Final approval before send email
#Send email

ROSTER_COMMENT = '#'
ROSTER_NBSP = '~'
ROSTER_GROUP = 'G'

RUBRIC_COMMENT = '#'
RUBRIC_FRONT_MATTER = '&'
RUBRIC_CATEGORY = '!'
RUBRIC_POINT_SEP = '~'

ROSTER_SAVE_SYMBOL = '?'
RUBRIC_SAVE_SEPARATOR = ':'
RUBRIC_FRONT_MATTER_SAVE_INDICATOR = '&'

TEX_FONT_SIZE = 12

def seeded_input(msg, text):
    readline.set_startup_hook(lambda: readline.insert_text(text))
    try:
        return input(msg)
    finally:
        readline.set_startup_hook()

#Class representing an entity that can be graded (student or group)
class GradedEntity:
    def __hash__(self):
        return hash(str(self))
    def __eq__(self, other):
        return type(self) == type(other) and str(self) == str(other)

#Class representing a group of students
#Use this class when BUILDING a group
class Group:
    def __init__(self, number):
        self.number = number
        self.students = set()

    def add_student(self, student):
        self.students.add(student)

#Class representing a group of students
#Immutable version of Group class
#Convert all groups to FrozenGroups before using
class FrozenGroup(GradedEntity):
    def __init__(self, group):
        self.number = group.number
        self.students = frozenset(group.students)

    def __str__(self):
        #return "Group %d (%s)"%(self.number, ', '.join([str(s) for s in self.students]))
        return "Group %d (%s)"%(self.number, ', '.join([str(st) for st in sorted(self.students, key = lambda s: s.lname + ' ' + s.fname)]))

    def __iter__(self):
        return iter(self.students)

    def __contains__(self, student):
        return student in self.students


#Class representing a student
#A student has a first name, a last name, and maybe an email address
class Student(GradedEntity):
    def __init__(self, fname, lname, email = None):
        self.fname = fname
        self.lname = lname
        self.email = email

    def __str__(self):
        if self.email is None:
            return "%s %s"%(self.fname, self.lname)
        else:
            return "%s %s %s"%(self.fname, self.lname, self.email)

#Convert a student and a prefix into a .tex name
def make_tex_name(prefix, student):
    return "%s_%s_%s.tex"%(prefix, student.lname, student.fname)

#Helpers for splittable
def in_char_range(char, a, b):
    return ord(char) >= ord(a) and ord(char) <= ord(b)

def is_splittable(char):
    return not in_char_range(char, 'a', 'z') and\
        not in_char_range(char, 'A', 'Z') and\
        not in_char_range(char, '0', '9') and char != '_' and char != ' '

#Make a word splittable in LaTeX
def make_tex_word(strg):
    ret = []
    for letter in strg:
        ret.append(letter)
        if is_splittable(letter):
            ret.append('{\\allowbreak}')
    return ''.join(ret)

#Class representing all the graded entities in the class
class Roster:
    #Constructor
    def __init__(self, from_file):
        #The set of all entities being graded (students or groups)
        self.graded_entities = set()
        #The set of all students
        self.students = set()
        #Are groups being used?
        self.using_groups = None
        #Rubrics
        self.rubrics = dict()
        #File for saving
        self.file = None
        #Open the file
        fd = open(from_file, 'r')
        line_counter = 0
        try:
            for line_long in fd:
                line_counter += 1
                #Strip preceding/trailing whitespace
                line = line_long.strip()
                #Ignore empty lines and comments
                if len(line) == 0 or line[0] == ROSTER_COMMENT:
                    continue
                #Split the line into pieces by whitespace
                tokens = line.split()
                #If we don't know whether we're using groups,
                #we should figure that out
                if self.using_groups is None:
                    #If groups are in use, line should start with G#
                    if re.match('^%s\\d+$'%ROSTER_GROUP, tokens[0]):
                        self.using_groups = True
                        #If groups are in use, initialize a group dictionary
                        #to use while building the groups
                        groups = dict()
                    else:
                        self.using_groups = False
                #If we're using groups, extract the group number
                if self.using_groups:
                    #Make sure the syntax is right
                    if not re.match('^%s\\d+$'%ROSTER_GROUP, tokens[0]):
                        raise ValueError("Invalid syntax in %s, Line %d: %s"%\
                            (from_file, line_counter, tokens[0]))
                    group_num = int(tokens[0][1:])
                    if group_num not in groups:
                        groups[group_num] = Group(group_num)
                    #Remove the group, so now it's the same
                    del tokens[0]
                if len(tokens) < 2:
                    raise ValueError("Invalid syntax in %s, Line %d: %s"%\
                            (from_file, line_counter, line_long))
                #Convert ~ to space
                #Important for people with spaces in their names
                tokens[0] = tokens[0].replace(ROSTER_NBSP," ")
                tokens[1] = tokens[1].replace(ROSTER_NBSP," ")
                #Create a Student
                student = Student(*tokens)
                if self.using_groups:
                    #If groups are in use, add the student to their group
                    groups[group_num].add_student(student)
                else:
                    #If groups are not in use, add the student as an entity
                    self.graded_entities.add(student)
                #Regardless, add the student as a student
                self.students.add(student)
        except:
            #Be sure to close the file if an error happens
            fd.close()
            print("An error occurred when building the Roster\n")
            raise
        #Close the file
        fd.close()
        #If groups are in use, freeze them
        if self.using_groups:
            for group in groups.values():
                self.graded_entities.add(FrozenGroup(group))

    def __str__(self):
        ret = ""
        for entity in self:
            ret += "%s\n"%str(entity)
        return ret

    def __iter__(self):
        def keyfn(ent):
            if isinstance(ent, FrozenGroup):
                return ent.number
            else:
                return ent.lname + ' ' + ent.fname
        return iter(sorted(self.graded_entities, key = keyfn))

    def get_students(self):
        return sorted(self.students, key = lambda s: s.lname + ' ' + s.fname)

    #Initialize a blank rubric for every graded entity
    def initialize_blank_rubrics(self, rubric):
        for entity in self.graded_entities:
            #Copy the rubric for the entity
            self.rubrics[entity] = Rubric(rubric)
            #In case the entity is a group, make non-group-respecting
            #categories tied to specific individuals
            self.rubrics[entity].individualize(entity)

    def is_using_groups(self):
        return self.using_groups

    def get_rubric(self, entity):
        if isinstance(entity, Student) and self.using_groups:
            for group in self.graded_entities:
                if entity in group:
                    return self.rubrics[group].customize(entity)
        else:
            return self.rubrics[entity]

    def get_group(self, student):
        for group in self.graded_entities:
            if student in group:
                return group

    #Get a student from the roster
    #If necessary, make it one whose grading is in progress or done
    #If can't do that, just return first student
    def get_a_student(self, only_finished = False, all = False):
        def rubric_is_ok(rubric):
            return all or rubric.is_filled() or (not only_finished and\
                rubric.is_in_progress())
        for student in self.get_students():
            rubric = self.get_rubric(student)
            if rubric_is_ok(rubric):
                return student
        return self.get_students()[0]

    #Save all the rubrics
    def save(self, file):
        global saved
        fd = open(file, 'w')
        try:
            for entity in self.graded_entities:
                fd.write("%s%s\n"%(ROSTER_SAVE_SYMBOL, str(entity)))
                fd.write("%s\n"%self.rubrics[entity].export_rubric())
        except:
            fd.close()
            raise
        fd.close()
        print("Successfully saved in %s\n"%file[file.rfind(os.sep)+1:])
        saved = True

    #Load all the rubrics
    def load(self, file):
        global saved
        fd = open(file, 'r')
        cur_entity = None
        buffer = ""
        def flush_buffer():
            nonlocal buffer
            if buffer != "":
                self.rubrics[cur_entity].import_rubric(buffer)
                buffer = ""
        try:
            for line in fd:
                line = line.strip()
                if len(line) == 0:
                    continue
                elif line[0] == ROSTER_SAVE_SYMBOL:
                    for entity in self.graded_entities:
                        if str(entity) == line[1:]:
                            flush_buffer()
                            cur_entity = entity
                            break
                else:
                    buffer += "%s\n"%line
            flush_buffer()
        except:
            fd.close()
            raise
        fd.close()
        print("%s loaded successfully\n"%file[file.rfind(os.sep)+1:])
        saved = True

    #Export grades into a CSV file
    def export_csv(self, csv_filename):
        fd = open(csv_filename, 'w')
        try:
            firstline = True
            for student in self.get_students():
                rubric = self.get_rubric(student)
                if firstline:
                    fd.write("%s,%s,%s\n"%("Last", "First",\
                        rubric.get_category_csv()))
                    firstline = False
                fd.write("%s,%s,%s\n"%(student.lname, student.fname,\
                    rubric.get_csv()))
        except:
            fd.close()
            raise
        fd.close()
        print("CSV %s written successfully\n"%csv_filename[csv_filename.rfind(os.sep)+1:])

    #Export rubrics into PDFs (via .tex files)
    def export_pdfs(self, pdf_prefix, only_finished = False, all = False, verbose = False):
        tex_files = []
        for student in self.get_students():
            rubric = self.get_rubric(student)
            if all or rubric.is_filled() or (not only_finished and\
                    rubric.is_in_progress()):
                #Include this one
                fname = make_tex_name(pdf_prefix, student)
                fd = open(fname, 'w')
                try:
                    fd.write("\\documentclass[%dpt]{article}\n"%TEX_FONT_SIZE)
                    fd.write("\\usepackage{fullpage}\n")
                    fd.write("\\usepackage[none]{hyphenat}\n")
                    fd.write("\\begin{document}\n\\noindent ")
                    if self.is_using_groups():
                        group = self.get_group(student)
                        fd.write("\\textbf{Group %d}\\\\\n"%group.number)
                        fd.write(rubric.get_front_matter_tex())
                        fd.write("\\textbf{Members:} %s\\\\\n"%', '.join(\
                            ['%s %s'%(s.fname, s.lname) for s in group]))
                        fd.write("\\textbf{Graded Member:} %s %s\\\\\n"%\
                            (student.fname, student.lname))
                    else:
                        fd.write("\\textbf{%s %s}\\\\\n"%(student.fname, student.lname))
                        fd.write(rubric.get_front_matter_tex())
                    fd.write("\n\\noindent\\begin{tabular}{|p{1.7in}|l|l|p{2.8in}|}\\hline\n")
                    fd.write("&\\textbf{TOTAL}&\\textbf{POINTS}&\\textbf{COMMENTS}\\\\\\hline\n")
                    fd.write(rubric.get_tex())
                    fd.write("\\end{tabular}\n")
                    fd.write("\\end{document}")
                except:
                    fd.close()
                    raise
                fd.close()
                tex_files.append(fname)
                if verbose:
                    print("%s written successfully"%fname[fname.rfind(os.sep)+1:])
        print("\nAll .tex files written successfully\n")
        #Now, compile all of them
        for tex_file in tex_files:
            dirc = tex_file[:tex_file.rfind(os.sep)]
            fname = tex_file[tex_file.rfind(os.sep)+1:-4] + '.pdf'
            #Remove any old file, if it exists
            if os.path.isfile(dirc + os.sep + fname):
                os.remove(dirc + os.sep + fname)
            args_tex = ['pdflatex', '-output-directory=%s'%dirc, '-halt-on-error', tex_file]
            if verbose:
                subprocess.run(args_tex)
            else:
                subprocess.run(args_tex, stdout=subprocess.DEVNULL)
            if not os.path.isfile(dirc + os.sep + fname):
                raise ValueError("%s failed to compile"%tex_file[tex_file.rfind(os.sep)+1:])
            if verbose:
                print("%s compiled successfully"%fname)
        if verbose:
            print()
        print("All .pdf files compiled successfully\n")


class ItemChangingText:
    def __init__(self, item):
        self.item = item

    def __str__(self):
        ret = self.item.get_name()
        if not self.item.has_own_field():
            if self.item.get_comment() != "":
                ret += " \"%s\""%self.item.get_comment()
        else:
            if self.item.get_score() is None:
                ret += " (out of %d)"%(self.item.get_value())
            else:
                ret += " (%d/%d)"%(self.item.get_score(), self.item.get_value())
            if self.item.get_comment() != "":
                ret += " \"%s\""%self.item.get_comment()
        return ret


#Class representing a grading item
class Item:
    next_id = 0
    def __init__(self, name, value):
        self.name = name
        self.value = value
        self.score = None
        self.comment = ""
        self.edit_menu = None
        self.id = Item.next_id
        Item.next_id += 1

    def set_comment(self, comment):
        global saved
        saved = False
        self.comment = comment

    def get_comment(self):
        return self.comment

    def set_score(self, score):
        global saved
        saved = False
        self.score = score

    def get_score(self):
        return self.score

    def get_value(self):
        return self.value

    def get_name(self):
        return self.name

    def __str__(self):
        ret = "%-20s%-3d"%(self.get_name(), self.get_value())
        if self.get_score() is not None:
            ret += "%-3d"%self.get_score()
        if self.comment is not None:
            ret += "%s"%self.comment
        return ret

    def copy(self, reference_student = None):
        new_item = Item(self.name, self.value)
        new_item.score = self.score
        new_item.comment = self.comment
        new_item.id = self.id
        return new_item

    def is_individual(self):
        return False

    def individualize(self, group):
        pass

    def get_individual(self):
        return None

    def get_id(self):
        return self.id

    def has_own_field(self):
        return True

    # def add_items_to_menu(self, menu):
    #     if self.edit_menu is None:
    #         self.edit_menu = EditMenu(self)
    #     #menu.add_item(self.get_name(), self.edit_menu.prompt)
    #     menu.add_item(ItemChangingText(self), self.edit_menu.prompt)

    # #If score is None, make it 100%
    # def fill_scores(self):
    #     if self.get_score() is None:
    #         self.set_score(self.get_value())

    def traverse(self, action, accum, ignore_blanks = True):
        if accum is None:
            action(self)
        else:
            accum(action(self))

#Class representing a grading category
class Category(Item):
    def __init__(self, name, value = None, respect_groups = True):
        super().__init__(name, value)
        self.items = []
        self.respect_groups = respect_groups
        self.individual = None
        self.children = dict()

    def add_item(self, item):
        self.items.append(item)

    def get_value(self):
        if len(self.items) == 0:
            return self.value
        return sum([item.get_value() for item in self.items])

    def get_score(self):
        if len(self.children) > 0:
            max_score = None
            for child in self.children.values():
                if child.get_score() is None:
                    return None
                elif max_score is None:
                    max_score = child.get_score()
                else:
                    max_score = max(max_score, child.get_score())
            return max_score
        if len(self.items) == 0:
            return self.score
        ret = 0
        for item in self.items:
            if item.get_score() is None:
                return None
            else:
                ret += item.get_score()
        return ret

    def get_name(self):
        nget = super().get_name()
        if self.individual is not None:
            nget += " [%s]"%(self.individual.fname + ' ' + self.individual.lname)
        return nget

    def is_individual(self):
        return not self.respect_groups

    def get_individual(self):
        return self.individual

    def individualize(self, group):
        if self.is_individual():
            #Need to alter this
            for student in group:
                individual_cat = self.copy()
                individual_cat.individual = student
                self.children[student] = individual_cat
        else:
            #Individualize children
            for item in self:
                item.individualize(group)

    def has_own_field(self):
        return self.value is not None

    def get_items(self):
        return self.items

    def __iter__(self):
        return iter(self.items)

    #Template for traversing all things that have values
    #and doing something with them
    def traverse(self, action, accum=None, ignore_blanks = True):
        if len(self.children) > 0:
            for child in self.children.values():
                child.traverse(action, accum, ignore_blanks)
        elif not ignore_blanks or self.has_own_field():
            #print("entering super")
            super().traverse(action, accum, ignore_blanks)
            #print("leaving super")
        for item in self:
            item.traverse(action, accum, ignore_blanks)

    def deep_str(self):
        if len(self.children) > 0:
            ret = "\n"
            for child in self.children.values():
                ret += child.deep_str() + '\n'
        else:
            ret = str(self)
            for item in self:
                if isinstance(item, Category):
                    ret += "\n\n%s"%item.deep_str()
                else:
                    ret += "\n%s"%str(item)
        return ret

    def copy(self, reference_student = None):
        #if reference_student is not None:
        #    print(reference_student)
        ref = self
        if reference_student is not None and reference_student in self.children:
            #Use this one
            ref = self.children[reference_student]
        new_cat = Category(ref.name, ref.value, ref.respect_groups)
        new_cat.score = ref.score
        new_cat.comment = ref.comment
        new_cat.children = dict()
        new_cat.id = ref.id
        #for key in self.children:
        #    new_cat.children[key] = self.children[key].copy()
        if reference_student is None:
            new_cat.individual = ref.individual
        for item in ref:
            new_cat.add_item(item.copy(reference_student))
        return new_cat

    # def add_items_to_menu(self, menu):
    #     #print("hello")
    #     #print(self)
    #     if len(self.children) > 0:
    #         #print("has children")
    #         #print(self.children)
    #         for child in self.children.values():
    #             child.add_items_to_menu(menu)
    #     elif self.has_own_field():
    #         #print("entering super")
    #         super().add_items_to_menu(menu)
    #         #print("leaving super")
    #     for item in self:
    #         item.add_items_to_menu(menu)
    #     #print("Done with ", self)
    #     #print()
    def add_items_to_menu(self, menu):
        def add_items_to_menu_action(item):
            if item.edit_menu is None:
                item.edit_menu = EditMenu(item)
            #menu.add_item(self.get_name(), self.edit_menu.prompt)
            menu.add_item(ItemChangingText(item), item.edit_menu.prompt)
        self.traverse(add_items_to_menu_action)

    # #Fill in all unfilled scores with 100%
    # def fill_scores(self):
    #     if len(self.children) > 0:
    #         for child in self.children.values():
    #             child.fill_scores()
    #     elif self.has_own_field():
    #         #print("entering super")
    #         super().fill_scores()
    #         #print("leaving super")
    #     for item in self:
    #         item.fill_scores()
    #Fill in all unfilled scores with 100%
    def fill_scores(self):
        def fill_scores_action(item):
            if item.get_score() is None:
                item.set_score(item.get_value())
        self.traverse(fill_scores_action)

class FrontmatterChangingText:
    def __init__(self, fm, fm_dict):
        self.fm = fm
        self.fm_dict = fm_dict

    def __str__(self):
        if fm_dict[fm] is None:
            return fm
        else:
            return "%s (\"%s\")"%(fm, fm_dict[fm])

#Class representing a rubric
class Rubric:
    #Constructor
    def __init__(self, from_file_or_rubric, reference_student = None):
        #Menus
        self.menu = None
        self.frontmatter_menu = None
        self.auto_comment_menu = None
        if isinstance(from_file_or_rubric, Rubric):
            #We're making a copy
            other = from_file_or_rubric
            self.frontmatter = list(other.frontmatter)
            self.frontmatter_dict = dict(other.frontmatter_dict)
            self.total = other.total.copy(reference_student)
            return
        #It's from a file
        from_file = from_file_or_rubric
        #Things that need to be manually entered (e.g. a title)
        self.frontmatter = []
        self.frontmatter_dict = dict()
        #List of categories
        self.total = Category("TOTAL")
        #Keep track of current category
        current_category = self.total
        #Open the file
        fd = open(from_file, 'r')
        line_counter = 0
        try:
            for line_long in fd:
                line_counter += 1
                #Strip preceding/trailing whitespace
                line = line_long.strip()
                #Ignore empty lines and comments
                if len(line) == 0 or line[0] == RUBRIC_COMMENT:
                    continue
                #Check if it's front matter
                if line[0] == RUBRIC_FRONT_MATTER:
                    self.frontmatter.append(line[1:])
                    self.frontmatter_dict[line[1:]] = None
                #Check if it's a category
                elif line[0] == RUBRIC_CATEGORY:
                    cat_name = line[1:]
                    #Check if we are an individual category
                    if len(cat_name) > 1 and cat_name[0] == RUBRIC_CATEGORY:
                        resp_groups = False
                        cat_name = cat_name[1:]
                    else:
                        resp_groups = True
                    #Determine whether the category has its own field
                    point_sep_idx = cat_name.rfind(RUBRIC_POINT_SEP)
                    if point_sep_idx == -1:
                        #No own field
                        #Create the current category
                        current_category = Category(cat_name, respect_groups = resp_groups)
                    else:
                        #Own field
                        try:
                            #Create the current category
                            current_category = Category(cat_name[:point_sep_idx],\
                                int(cat_name[point_sep_idx+1:]), respect_groups = resp_groups)
                        except ValueError:
                            #Syntax error in file; not an integer for value
                            print("Invalid syntax in %s, Line %d: %s"%\
                                (from_file, line_counter, cat_name[point_sep_idx:]))
                            raise
                    #Append the current category to the list of categories
                    #self.categories.append(current_category)
                    self.total.add_item(current_category)
                #Otherwise, it's an item
                else:
                    #Check for orphan item
                    if current_category == self.total:
                        print("Warning: Item without category "\
                            "in %s, Line %d: %s"%(from_file, line_counter, line_long))
                    #Make sure this item has a value
                    point_sep_idx = line.rfind(RUBRIC_POINT_SEP)
                    if point_sep_idx == -1:
                        #Nope! Error!
                        raise ValueError("Invalid syntax (item without value) "\
                            "in %s, Line %d: %s"%(from_file, line_counter, line_long))
                    #Add a new item
                    try:
                        current_category.add_item(Item(line[:point_sep_idx],\
                            int(line[point_sep_idx+1:])))
                    except ValueError:
                        #Syntax error in file; not an integer for value
                        print("Invalid syntax in %s, Line %d: %s"%\
                            (from_file, line_counter, line[point_sep_idx:]))
                        raise
        except:
            #Be sure to close the file if an error happens
            fd.close()
            print("An error occurred when building the Rubric\n")
            raise
        #Close the file
        fd.close()

    def __str__(self):
        # ret = '%s\n'%('\n'.join(self.frontmatter))
        # #for category in self.categories:
        # for category in self.total:
        #     ret += '\nCATEGORY: %s'%str(category)
        #     for item in category:
        #         ret += "\n%s"%str(item)
        # ret += '\n%s'%str(self.total)
        # return ret
        ret = ''
        for fm in self.frontmatter:
            if self.frontmatter_dict[fm] is None:
                ret += "%s: (empty)\n"%fm
            else:
                ret += "%s: %s\n"%(fm, self.frontmatter_dict[fm])
        return ret + self.total.deep_str()

    #If graded_entity is a FrozenGroup, find all non-group-respecting Categories
    #and replace them with one per individual
    #If graded_entity is a Student, do nothing
    def individualize(self, graded_entity):
        if isinstance(graded_entity, FrozenGroup):
            self.total.individualize(graded_entity)

    #Create a copy of this rubric
    #Then, modify the copy to only use children defined by the given student
    def customize(self, student):
        return Rubric(self, student)

    def full_front_matter(self):
        for fm in self.frontmatter:
            if self.frontmatter_dict[fm] is None:
                return False
        return True

    def some_front_matter(self):
        for fm in self.frontmatter:
            if self.frontmatter_dict[fm] is not None:
                return True
        return False

    def is_filled(self):
        return self.total.get_score() is not None

    def is_in_progress(self):
        def checker(item):
            return item.get_score() is not None or item.get_comment() != ''
        ret = False
        def accumulator(add_bool):
            nonlocal ret
            ret = ret or add_bool
        self.total.traverse(checker, accumulator, ignore_blanks = False)
        return ret

    def is_auto_comment_in_progress(self):
        def checker(item):
            return not item.has_own_field() and item.get_comment() != ''
        ret = False
        def accumulator(add_bool):
            nonlocal ret
            ret = ret or add_bool
        self.total.traverse(checker, accumulator, ignore_blanks = False)
        return ret

    #Set front matter for this rubric
    def set_front_matter(self):
        global saved
        def modify_front_matter(label):
            fm_text = self.frontmatter_dict[label]
            if fm_text is None:
                fm_text = ""
            val = seeded_input("Enter value for \"%s\", or 0 to cancel: "\
                %label, fm_text)
            if val == '0':
                print("Canceled")
                return
            else:
                saved = False
                self.frontmatter_dict[label] = val
        if len(self.frontmatter) == 1:
            modify_front_matter(self.frontmatter[0])
        elif self.frontmatter_menu is None:
            self.frontmatter_menu = Menu("Select item:", menued = False)
            for fm in self.frontmatter:
                self.frontmatter_menu.add_item(FrontmatterChangingText(fm,\
                    self.frontmatter_dict), modify_front_matter, fm)

    #Add a comment to a category with no field for itself
    def add_auto_comment(self):
        if self.auto_comment_menu is None:
            self.auto_comment_menu = Menu("Select category to add comment to:", menued = False)
            def auto_comment(item):
                old_comment = item.get_comment()
                comment = seeded_input("Enter comment for %s, or 0 to cancel: "\
                %item.get_name(), old_comment)
                if comment == '0':
                    print("Canceled")
                    return
                item.set_comment(comment)
            def traverser(item):
                if not item.has_own_field():
                    return self.auto_comment_menu.add_item(ItemChangingText(item),\
                        auto_comment, item)
            self.total.traverse(traverser, ignore_blanks = False)
        self.auto_comment_menu.prompt()


    #Build a menu out of this rubric
    def get_menu(self):
        if self.menu is not None:
            return self.menu
        self.menu = Menu("Select an item/category:")
        if len(self.frontmatter) > 0:
            def fm_update_text():
                if len(self.frontmatter) == 1:
                    return "Update Front Matter (%s = \"%s\")"%(self.frontmatter[0],\
                        self.frontmatter_dict[self.frontmatter[0]])
                else:
                    todo_fm = []
                    for fm in self.frontmatter:
                        if self.frontmatter_dict[fm] is None:
                            todo_fm.append(fm)
                    if len(todo_fm) == 0:
                        return "Update Front Matter"
                    else:
                        return "Update/Set Front Matter (%s)"%(', '.join(todo_fm))
            fm_set = "Set Front Matter"
            if len(self.frontmatter) == 1:
                fm_set += ' (%s)'%self.frontmatter[0]
            self.menu.add_item(ChangingText(fm_update_text, fm_set,\
                self.some_front_matter), self.set_front_matter)
        self.total.add_items_to_menu(self.menu)
        self.menu.add_item(ChangingText("Add comment to auto-scored category (in progress)",\
            "Add comment to auto-scored category", self.is_auto_comment_in_progress),\
            self.add_auto_comment)
        self.menu.add_item("Set rest to 100%", self.total.fill_scores)
        return self.menu

    def grade(self):
        #return self.get_menu().prompt()
        MenuManager.get_menu_manager().add_menu(self.get_menu())

    #Convert to a string that can be imported
    def export_rubric(self):
        def transcriber(item):
            if item.has_own_field() and (item.get_score() is not None or\
                    item.get_comment() != ''):
                if item.get_individual() is not None:
                    if item.get_score() is not None:
                        return "%d%s%s%s%d%s%s\n"%(item.get_id(), RUBRIC_SAVE_SEPARATOR,\
                            str(item.get_individual()), RUBRIC_SAVE_SEPARATOR,\
                            item.get_score(), RUBRIC_SAVE_SEPARATOR, item.get_comment())
                    else:
                        return "%d%s%s%s%s%s\n"%(item.get_id(), RUBRIC_SAVE_SEPARATOR,\
                            str(item.get_individual()), RUBRIC_SAVE_SEPARATOR,\
                            RUBRIC_SAVE_SEPARATOR, item.get_comment())
                else:
                    if item.get_score() is not None:
                        return "%d%s%d%s%s\n"%(item.get_id(), RUBRIC_SAVE_SEPARATOR,\
                            item.get_score(), RUBRIC_SAVE_SEPARATOR, item.get_comment())
                    else:
                        return "%d%s%s%s\n"%(item.get_id(), RUBRIC_SAVE_SEPARATOR,\
                            RUBRIC_SAVE_SEPARATOR, item.get_comment())
            elif not item.has_own_field() and item.get_comment() != '':
                if item.get_individual() is not None:
                    return "%d%s%s%s%s%s\n"%(item.get_id(), RUBRIC_SAVE_SEPARATOR,\
                        str(item.get_individual()), RUBRIC_SAVE_SEPARATOR,\
                        RUBRIC_SAVE_SEPARATOR, item.get_comment())
                else:
                    return "%d%s%s%s\n"%(item.get_id(), RUBRIC_SAVE_SEPARATOR,\
                        RUBRIC_SAVE_SEPARATOR, item.get_comment())
            else:
                return ""
        ret = ""
        #Front matter
        for fm in self.frontmatter:
            fdv = self.frontmatter_dict[fm]
            if fdv is not None:
                ret += '%s%s%s%s\n'%(RUBRIC_FRONT_MATTER_SAVE_INDICATOR, fm,\
                    RUBRIC_SAVE_SEPARATOR, fdv)
        def accumulator(add_str):
            nonlocal ret
            ret += add_str
        self.total.traverse(transcriber, accumulator, ignore_blanks = False)
        return ret

    #Import a string created by export
    def import_rubric(self, rubric_repr):
        #Read in the things that need to be imported
        lines = rubric_repr.split('\n')
        insertions = dict()
        for line in lines:
            if line.strip() == '':
                continue
            line_pieces = line.split(RUBRIC_SAVE_SEPARATOR)
            if line_pieces[0][0] == RUBRIC_FRONT_MATTER_SAVE_INDICATOR:
                #Front matter
                self.frontmatter_dict[line_pieces[0][1:]] = line_pieces[1]
                continue
            the_id = int(line_pieces[0])
            if not (len(line_pieces[1]) == 0 or line_pieces[1].isdecimal()\
                    or (line_pieces[1][0] == '-' and line_pieces[1][1:].isdecimal())):
                #We have an individualized thing
                individual_str = line_pieces[1]
                del line_pieces[1]
            else:
                individual_str = None
            the_score = line_pieces[1]
            if the_score == '':
                the_score = None
            else:
                the_score = int(the_score)
            the_comment = RUBRIC_SAVE_SEPARATOR.join(line_pieces[2:])
            insertions[(the_id, individual_str)] = (the_score, the_comment)
        #Actually do the importing
        def importer(item):
            nonlocal insertions
            if item.get_individual() is None:
                key = (item.get_id(), None)
            else:
                key = (item.get_id(), str(item.get_individual()))
            if key in insertions:
                #Insert it!
                if item.has_own_field():
                    item.set_score(insertions[key][0])
                item.set_comment(insertions[key][1])
                del insertions[key]
        self.total.traverse(importer, ignore_blanks = False)

    #Get comma-separated list of categories
    def get_category_csv(self):
        def traverser(item):
            if isinstance(item, Category):
                return item.get_name()
            else:
                return None
        ret = []
        def accumulator(add_str):
            if add_str is not None:
                ret.append(add_str)
        self.total.traverse(traverser, accumulator, ignore_blanks = False)
        return ','.join(ret)

    #Get comma-separated list of scores
    def get_csv(self):
        def traverser(item):
            if isinstance(item, Category):
                if item.get_score() is None:
                    return ""
                else:
                    return str(item.get_score())
            else:
                return None
        ret = []
        def accumulator(add_str):
            if add_str is not None:
                ret.append(add_str)
        self.total.traverse(traverser, accumulator, ignore_blanks = False)
        return ','.join(ret)

    #Get LaTeX for front matter
    def get_front_matter_tex(self):
        ret = ''
        for fm in self.frontmatter:
            fm_val = self.frontmatter_dict[fm]
            if fm_val is not None:
                ret += "\\textbf{%s:} %s\\\\\n"%(fm, fm_val)
        return ret

    #Get LaTeX for grade table
    def get_tex(self):
        ret = []
        def traverser(item):
            score = item.get_score()
            if score is None:
                score = ""
            else:
                score = str(score)
            if item == self.total:
                ret.append("{\\Large \\textbf{%s}}&{\\Large \\textbf{%d}}&{\\Large \\textbf{%s}}&%s\\\\\\hline\n"\
                    %(make_tex_word(item.get_name()), item.get_value(),\
                    score, make_tex_word(item.get_comment())))
                return
            elif isinstance(item, Category):
                str1 = "\\textbf{"
                str2 = "}"
                ret.append("&&&\\\\\\hline\n")
            else:
                str1 = ""
                str2 = ""
            ret.append("\\textbf{%s}&%s%d%s&%s%s%s&%s\\\\\\hline\n"%\
                (make_tex_word(item.get_name()), str1, item.get_value(), str2, str1, score,\
                str2, make_tex_word(item.get_comment())))
        self.total.traverse(traverser, ignore_blanks = False)
        ret.append("&&&\\\\\\hline\n")
        itm = ret[0]
        del ret[0]
        ret.append(itm)
        del ret[0]
        return '\n'.join(ret) + '\n'

#Class representing a menu item
class MenuItem:
    def __init__(self, text, callback, *args):
        self.text = text
        self.callback = callback
        self.args = args

    #The item was chosen
    #Do whatever it is designed to do
    def evoke(self):
        return self.callback(*self.args)

    def __str__(self):
        return str(self.text)

#Class representing a menu that can be
#accessed via the Command Line
class Menu:
    def __init__(self, message, min_item = 0, back = True, menued = True):
        self.message = message
        self.items = []
        self.min_item = min_item
        if back:
            if menued:
                self.add_item("Back", MenuManager.get_menu_manager().pop)
            else:
                self.add_item("Back", lambda : None)

    def __str__(self):
        ret = self.message
        lenitems = len(str(len(self.items)-1+self.min_item))
        for i in range(len(self.items)):
            ret += "\n%*d: %s"%(lenitems, i+self.min_item, str(self.items[i]))
        return ret

    #Prompt the user for one of the items in the menu
    #Keep prompting until something valid is entered
    def prompt(self):
        if len(self.items) == 0:
            #There are no items
            #Prevent deadlock
            raise ValueError("No items in menu")
        print(self)
        print()
        while True:
            ipt = input(">>>> ")
            try:
                if len(ipt) == 0:
                    chosen_item = self.min_item
                else:
                    chosen_item = int(ipt)
                if chosen_item < self.min_item:
                    raise ValueError("Value entered too small: %d"%chosen_item)
                elif chosen_item >= len(self.items) + self.min_item:
                    raise ValueError("Value entered too large: %d"%chosen_item)
                else:
                    break
            except ValueError as err:
                print(err)
                print("Try Again\n")
        return self.items[chosen_item - self.min_item].evoke()

    #Add an item to this menu
    def add_item(self, text, callback, *args):
        self.items.append(MenuItem(text, callback, *args))

def assign_grade(item):
    print("Grading %s, out of %d"%(item.get_name(), item.get_value()))
    msg = "Please enter grade, blank to clear, or a non-number to cancel: "
    try:
        old_grade = item.get_score()
        if old_grade is None:
            old_grade = ""
        else:
            old_grade = str(old_grade)
        grade = seeded_input(msg, old_grade)
        if len(grade) == 0:
            item.set_score(None)
        else:
            if "." in grade:
                grade = float(grade)
            else:
                grade = int(grade)
            item.set_score(grade)
    except ValueError:
        print("Canceled")
        pass

def assign_comment(item):
    if item.get_score() is not None:
        print("Comment for %s, score of %d/%d"%(item.get_name(),\
            item.get_score(), item.get_value()))
    else:
        print("Comment for %s, score TBD"%item.get_name())
    msg = "Please enter comment, or 0 to cancel: "
    old_comment = item.get_comment()
    comment = seeded_input(msg, old_comment)
    if comment == '0':
        print("Canceled")
    else:
        item.set_comment(comment)

def function_sequencer(funcs, *args):
    for func in funcs:
        func(*args)

class ChangingText:
    def __init__(self, text1, text2, conditional, *args):
        self.text1 = text1
        self.text2 = text2
        self.conditional = conditional
        self.args = args

    def __str__(self):
        if self.conditional(*self.args):
            if isinstance(self.text1, collections.Callable):
                return self.text1(*self.args)
            else:
                return self.text1
        else:
            if isinstance(self.text2, collections.Callable):
                return self.text2(*self.args)
            else:
                return self.text2

class EditMenu(Menu):
    def __init__(self, grade_item):
        super().__init__("Action on %s:"%grade_item.get_name(), menued = False)
        self.add_item(ChangingText("Grade", lambda item:\
            "Update Grade (%d/%d)"%(item.get_score(), item.get_value()),\
            lambda item: item.get_score() is None, grade_item),\
            assign_grade, grade_item)
        self.add_item(ChangingText("Comment", lambda item:\
            "Update Comment (\"%s\")"%item.get_comment(),\
            lambda item: item.get_comment() == "", grade_item),\
            assign_comment, grade_item)
        # grade_str = "Grade"
        # if grade_item.get_score() is not None:
        #     grade_str = "Update Grade"
        # self.add_item(grade_str, assign_grade, grade_item)
        # comment_str = "Comment"
        # if grade_item.get_comment() != "":
        #     comment_str = "Update Comment"
        # self.add_item(comment_str, assign_comment, grade_item)
        self.add_item("Both", function_sequencer,\
            [assign_grade, assign_comment], grade_item)

class MenuManager:
    manager = None
    @staticmethod
    def get_menu_manager():
        if MenuManager.manager is None:
            MenuManager.manager = MenuManager()
        return MenuManager.manager

    def __init__(self):
        self.menu_stack = []

    def add_menu(self, menu):
        self.menu_stack.append(menu)

    def pop(self):
        return self.menu_stack.pop()

    def mainloop(self):
        while len(self.menu_stack) > 0:
            self.menu_stack[-1].prompt()

class FileManager:
    FILE_KEY = "FILE"
    CSV_KEY = "CSV"
    PDF_KEY = "PDF"
    def __init__(self, dirc):
        self.directory = dirc
        if self.directory[-1] != os.sep:
            self.directory += os.sep
        self.files = dict({FileManager.FILE_KEY:None, FileManager.CSV_KEY:None,\
            FileManager.PDF_KEY:None})

    def get_cond_file(self, msg, key, exister = lambda a,s: a + s,\
            confirmer = "Warning: %s already exists. Overwrite?",
            returner = lambda a,s: a + s, save_as = False):
        if save_as or self.files[key] is None:
            fil = input(msg)
            if os.path.isfile(exister(self.directory, fil)):
                #Confirm overwriting file
                confirmed = False
                def confirm(to_confirm):
                    nonlocal confirmed
                    confirmed = to_confirm
                confirm_menu = Menu(confirmer%fil, back = False)
                confirm_menu.add_item("Yes", confirm, True)
                confirm_menu.add_item("No", confirm, False)
                confirm_menu.prompt()
                if not confirmed:
                    return None
            self.files[key] = fil
        return returner(self.directory, self.files[key])

    def get_save_file(self, save_as = False):
        return self.get_cond_file("File to save into: ", FileManager.FILE_KEY,\
            save_as = save_as)
        # if save_as or self.file is None:
        #     fil = input("File to save into: ")
        #     if os.path.isfile(self.directory + fil):
        #         #Confirm overwriting file
        #         confirmed = False
        #         def confirm(to_confirm):
        #             nonlocal confirmed
        #             confirmed = to_confirm
        #         confirm_menu = Menu("Warning: %s already exists. Overwrite?",\
        #             back = False)
        #         confirm_menu.add_item("Yes", confirm, True)
        #         confirm_menu.add_item("No", confirm, False)
        #         confirm_menu.prompt()
        #         if not confirmed:
        #             return None
        #     self.file = fil
        # return self.directory + self.file

    def get_open_file(self):
        fil = input("File to open: ")
        if not os.path.isfile(self.directory + fil):
            raise FileNotFoundError("File %s not found"%fil)
        self.files[FileManager.FILE_KEY] = fil
        return self.directory + self.files[FileManager.FILE_KEY]

    def get_export_file(self, save_as = False):
        return self.get_cond_file("File to export into: ", FileManager.CSV_KEY,\
            save_as = save_as)

    def get_pdf_prefix(self, student, save_as = False):
        return self.get_cond_file("PDF prefix to use: ", FileManager.PDF_KEY,\
            exister = lambda a, s: a + make_tex_name(s, student),\
            confirmer = "Warning: Prefix %s already in use. Overwrite?")
            #, returner = lambda a, s: s, save_as = save_as)

def print_delay(stuff):
    print(stuff)
    input("Press [ENTER] to continue...")

if __name__ == '__main__':
    #Should have at least four arguments
    #One should be -r
    #One should be -s
    #After -r should be rubric file
    #After -s should be students file
    #Can also have -v (verbose)
    #Can also have -o
    #-o followed by folder where stuff should be stored (default is current dir)
    rubric_file = None
    student_file = None
    verbose = False
    out_dir = '.'
    usage_str = 'usage: python3 rubric-grading.py -r rubric_file -s '\
        'student_file [-v] [-o output directory]\n'
    if len(sys.argv) == 1:
        #No arguments provided
        #Display usage string
        print(usage_str)
        sys.exit(0)
    flag = None
    for arg in sys.argv[1:]:
        if arg[0] == '-':
            if arg == '-v':
                verbose = True
            else:
                flag = arg
        else:
            if flag == '-r':
                rubric_file = arg
            elif flag == '-s':
                student_file = arg
            elif flag == '-o':
                out_dir = arg
            else:
                print('Unexpected argument: %s'%arg)
                print(usage_str)
                sys.exit(0)
            flag = None
    if rubric_file is None:
        print('Error: No rubric provided')
        print(usage_str)
        sys.exit(0)
    if student_file is None:
        print('Error: No students provided')
        print(usage_str)
        sys.exit(0)

    #Build the roster
    roster = Roster(student_file)
    if verbose:
        print("Roster:")
        print(roster)

    #Build the rubric
    rubric = Rubric(rubric_file)
    if verbose:
        print("Rubric:")
        print(rubric)

    #Initialize blank rubrics
    roster.initialize_blank_rubrics(rubric)
    if verbose:
        print("Blank rubrics initialized")

    #Stuff for saving when exiting
    file_manager = FileManager(out_dir)
    def save(save_as=False):
        fil = file_manager.get_save_file(save_as)
        if fil is not None:
            roster.save(fil)
            return True
        else:
            return False

    def save_and_exit():
        if save():
            sys.exit(0)

    saved = True
    def exit_with_save_prompt():
        global saved
        if not saved:
            save_warning_menu = Menu("Quit and lose unsaved changes?", back = False)
            save_warning_menu.add_item("Save and Quit", save_and_exit)
            save_warning_menu.add_item("Cancel", lambda : None)
            save_warning_menu.add_item("Quit without Saving", sys.exit, 0)
            save_warning_menu.prompt()
        else:
            sys.exit(0)

    def load():
        try:
            fil = file_manager.get_open_file()
        except FileNotFoundError as err:
            print("Error: %s\n"%str(err))
            return
        roster.load(fil)

    def save_and_load():
        if save():
            load()

    def load_with_save_prompt():
        global saved
        if not saved:
            save_warning_menu = Menu("Overwrite unsaved changes?", back = False)
            save_warning_menu.add_item("Save then Load", save_and_load)
            save_warning_menu.add_item("Cancel", lambda : None)
            save_warning_menu.add_item("Load and Overwrite", load)
            save_warning_menu.prompt()
        else:
            load()

    def is_saved():
        global saved
        return saved

    #Build the menu
    menu_manager = MenuManager.get_menu_manager()
    #Class used to update menu text when things are graded
    class MenuEntityTextUpdater:
        def __init__(self, entity):
            self.entity = entity

        def __str__(self):
            ret = str(self.entity)
            tack = None
            if roster.get_rubric(self.entity).is_filled():
                #ret = '(done) ' + ret
                tack = 'done'
            elif roster.get_rubric(self.entity).is_in_progress() or\
                    roster.get_rubric(self.entity).some_front_matter():
                #ret = '(in progress) ' + ret
                tack = 'in progress'
            if tack is not None:
                if not roster.get_rubric(self.entity).full_front_matter():
                    tack += '*'
                ret = '(%s) '%tack + ret
            return ret

    main_menu = Menu("What would you like to do?", back = False)
    main_menu.add_item(ChangingText("Quit", "Quit*", is_saved), exit_with_save_prompt)
    main_menu.add_item("Display Roster", print_delay, roster)
    main_menu.add_item("Display Rubric", print_delay, rubric)
    #Menu for viewing student rubrics
    student_menu = Menu("Select a student:", menued = False)
    def print_rubric(entity):
        print_delay(roster.get_rubric(entity))
    for student in roster.get_students():
        student_menu.add_item(MenuEntityTextUpdater(student), print_rubric, student)
    #main_menu.add_item("View Rubric by Student", menu_manager.add_menu, student_menu)
    main_menu.add_item("View Rubric by Student", student_menu.prompt)
    if roster.is_using_groups():
        #Menu for viewing group rubrics
        group_menu = Menu("Select a group:", menued = False)
        for group in roster:
            group_menu.add_item(MenuEntityTextUpdater(group), print_rubric, group)
        #main_menu.add_item("View Rubric by Group", menu_manager.add_menu, group_menu)
        main_menu.add_item("View Rubric by Group", group_menu.prompt)
        #Menu for editing rubrics
        grade_menu = Menu("Select a group:")
        for group in roster:
            grade_menu.add_item(MenuEntityTextUpdater(group),\
                roster.get_rubric(group).grade)
        main_menu.add_item("Grade a group", menu_manager.add_menu, grade_menu)
    else:
        #Menu for editing rubrics
        grade_menu = Menu("Select a student:")
        for student in roster:
            grade_menu.add_item(MenuEntityTextUpdater(student),\
                roster.get_rubric(student).grade)
        main_menu.add_item("Grade a student", menu_manager.add_menu, grade_menu)

    #Menu items for saving and loading
    main_menu.add_item("Save", save, False)
    main_menu.add_item("Save As", save, True)
    main_menu.add_item(ChangingText("Load", "Load*", is_saved), load_with_save_prompt)

    #Export CSV
    def export_csv(save_as):
        fil = file_manager.get_export_file(save_as)
        if fil is not None:
            roster.export_csv(fil)
    main_menu.add_item("Export CSV", export_csv, False)
    main_menu.add_item("Export CSV as", export_csv, True)

    #Export PDFs
    pdf_menu = Menu("Export: ", back = False)
    pdf_menu.add_item("Cancel", lambda : None)
    pdf_flag_list = ["Completed", "In Progress", "All"]
    pdf_save_as = False
    def export_pdf(flag):
        fil = file_manager.get_pdf_prefix(roster.get_a_student(only_finished =\
            flag == pdf_flag_list[0], all = flag == pdf_flag_list[-1]),\
            pdf_save_as)
        if fil is not None:
            roster.export_pdfs(fil, only_finished = flag == pdf_flag_list[0],\
                all = flag == pdf_flag_list[-1], verbose = verbose)
    for flag in pdf_flag_list:
        pdf_menu.add_item(flag, export_pdf, flag)
    def prompt_pdf(save_as):
        global pdf_save_as
        pdf_save_as = save_as
        pdf_menu.prompt()
    main_menu.add_item("Export PDFs", prompt_pdf, False)
    main_menu.add_item("Export PDFs as", prompt_pdf, True)

    menu_manager.add_menu(main_menu)
    menu_manager.mainloop()
