import sys
import os
import re
import readline
import collections.abc
import subprocess
import webbrowser

import email.message
import imaplib
import smtplib
import time
import getpass
import mimetypes

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
RUBRIC_ATTACHMENT_INDICATOR = '$'

EMAIL_CONFIG_COMMENT = '#'

TEX_FONT_SIZE = 12

if 'libedit' in readline.__doc__:
    readline.parse_and_bind("bind ^I rl_complete")
    libedit = True
    #print("Warning: Using libedit readline. Some advanced features may work suboptimally.\n")
else:
    readline.parse_and_bind("tab: complete")
    libedit = False

def seeded_input(msg, text = ""):
    if text != "":
        if libedit:
            #Mac
            #Make it so can hit up-arrow to get last value
            readline.add_history(text)
        else:
            #Non-Mac
            #Literally make it last value
            readline.set_startup_hook(lambda: readline.insert_text(text))
    try:
        return input(msg)
    finally:
        readline.set_startup_hook()

#Input, but where the eligible files are loaded into history
#and then unloaded afterward
#extension of '' matches file with no extension
#extension of None matches all files
def files_input(msg, dirc = '.', extensions = ['', '.txt']):
    #Get all the relevant files
    the_files = []
    last_seed = -1
    def load_files(seed):
        nonlocal the_files
        nonlocal last_seed
        nonlocal dirc
        #Make sure we're not tying up resources
        seed = seed.strip()
        if seed == last_seed:
            return
        last_seed = seed
        the_files = []
        #print("\n", seed)
        #Find out what directory we're in
        last_sep = seed.rfind(os.sep)
        #print(last_sep)
        if last_sep == -1:
            the_dirc = dirc
            tdir = ""
        elif seed[0] != os.sep:
            the_dirc = dirc + seed[:last_sep]
            tdir = seed[:last_sep+1]
        else:
            #print("hi")
            the_dirc = seed[:last_sep]
            tdir = seed[:last_sep+1]
            #print(the_dirc, tdir, "bye")
        if len(the_dirc) == 0 or the_dirc[-1] != os.sep:
            the_dirc += os.sep
        #Make sure we actually have a directory
        if not os.path.isdir(the_dirc):
            #We don't
            return
        #print(last_sep, the_dirc, tdir)
        #Load the files
        for fil in os.listdir(the_dirc):
            #Include directories
            if os.path.isdir(the_dirc + fil):
                the_files.append(tdir + fil + os.sep)
            else:
                for extension in extensions:
                    #Is it a file we care about?
                    if extension is None or (extension == '' and fil.find('.') == -1) \
                            or fil[-len(extension):] == extension:
                        #Make sure it's a file
                        if os.path.isfile(the_dirc + fil):
                            the_files.append(tdir + fil)
                        break
        #print(the_files)
        #print(seed)

    ##Get all the relevant files
    #the_files = []
    #the_dirc = dirc
    #if the_dirc[-1] != os.sep:
    #    the_dirc += os.sep
    #for fil in os.listdir(dirc):
    #    for extension in extensions:
    #        #Is it a file we care about?
    #        if extension is None or (extension == '' and fil.find('.') == -1) \
    #                or fil[-len(extension):] == extension:
    #            #Make sure it's not a directory
    #            if os.path.isfile(the_dirc + fil):
    #                the_files.append(fil)
    #            break

    #Completer
    def listCompleter(text, state):
        #Get the files
        load_files(text)

        line   = readline.get_line_buffer()

        if not line:
            return [c  for c in the_files][state]

        else:
            return [c  for c in the_files if c.startswith(line)][state]

    readline.set_completer(listCompleter)
    try:
        ret = input(msg)
    finally:
        readline.set_completer()

    #un-escape spaces
    ret = ret.replace("\\ ", " ")

    return ret

#Process a string to, in particular, replace \\n with \n
def unquote(strg, latexify = False):
    if latexify:
        un_strg = strg
        #un_strg = unquote(strg)
        #Replace \n with \\
        un_strg = un_strg.replace("\\n", "\\\n")
        #Replace \ with \backslash
        un_strg = un_strg.replace("\\", "\\textbackslash ")
        #Replace ^ with \textasciicircum
        un_strg = un_strg.replace("^", "\\textasciicircum ")
        #Replace ~ with \textasciitilde
        un_strg = un_strg.replace("~", "\\textasciitilde ")
        #Escape some things in LaTeX
        un_strg = un_strg.replace("_", "\\_")
        un_strg = un_strg.replace("$", "\\$")
        un_strg = un_strg.replace("{", "\\{")
        un_strg = un_strg.replace("}", "\\}")
        un_strg = un_strg.replace("#", "\\#")
        un_strg = un_strg.replace("%", "\\%")
        un_strg = un_strg.replace("&", "\\&")
        return un_strg
    return eval('"%s"'%strg)

def is_number(strg):
    try:
        int(strg)
    except:
        try:
            float(strg)
        except:
            return False
    return True

#Print an email message
def print_email(email_msg):
    print()
    for header in email_msg.items():
        print("%s: %s"%(header[0], header[1]))
    print()
    print(email_msg.get_body())
    print()
    for att in email_msg.iter_attachments():
        print("Attachment [type=%s, filename=%s]"%(att.get_content_type(),\
            att.get_filename()))
    print()

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
        self.students = tuple(sorted(group.students, key = lambda s: s.lname +\
            ' ' + s.fname))
        self.student_set = frozenset(group.students)

    def __str__(self):
        return "Group %d (%s)"%(self.number, ', '.join([str(s) for s in\
            self.students]))
        #return "Group %d (%s)"%(self.number, ', '.join([str(st) for st in\
        #    sorted(self.students, key = lambda s: s.lname + ' ' + s.fname)]))

    def __iter__(self):
        return iter(self.students)

    def __contains__(self, student):
        return student in self.student_set


#Class representing a student
#A student has a first name, a last name, and maybe an email address
class Student(GradedEntity):
    def __init__(self, fname, lname, email = None):
        self.fname = fname
        self.lname = lname
        self.email = email

    def __str__(self):
        #if self.email is None:
        return "%s %s"%(self.fname, self.lname)
        #else:
        #    return "%s %s %s"%(self.fname, self.lname, self.email)

    #Does this student have an email address?
    def has_email(self):
        return self.email is not None

#Convert a student and a prefix into a .tex name
def make_file_name(prefix, student, extension=None):
    if extension is None:
        return "%s_%s_%s"%(prefix, student.lname, student.fname)
    else:
        return "%s_%s_%s.%s"%(prefix, student.lname, student.fname, extension)

def make_tex_name(prefix, student):
    return make_file_name(prefix, student, 'tex')

def make_pdf_name(prefix, student):
    return make_file_name(prefix, student, 'pdf')

#Helpers for splittable
def in_char_range(char, a, b):
    return ord(char) >= ord(a) and ord(char) <= ord(b)

def is_splittable(char):
    return not in_char_range(char, 'a', 'z') and\
        not in_char_range(char, 'A', 'Z') and\
        not in_char_range(char, '0', '9') and char != '_' and char != ' '\
        and char != '\\'

#Make a word splittable in LaTeX
def make_tex_word(strg):
    ret = []
    for letter in unquote(strg, latexify=True):
        ret.append(letter)
        if is_splittable(letter):
            ret.append('{\\allowbreak}')
    return ''.join(ret)

#Class representing an email template
class EmailTemplate:
    def __init__(self, message = None, closing = None, subject = None,\
            my_email = None, my_name = None, greeting = "Dear %s,",
            pdf_prefix = "", attachments = []):
        self.message = message
        self.closing = closing
        self.greeting = greeting
        self.pdf_prefix = pdf_prefix
        self.subject = subject
        self.from_email = my_email
        self.from_name = my_name
        self.attachments = []

    #Prepare an email to the given student
    def render(self, student, message = None, attachments = []):
        body = message
        if body is None:
            body = self.message
        # the_directory = dirc
        # if the_directory[-1] != os.sep:
        #     the_directory += os.sep
        email_msg = email.message.EmailMessage()
        if "%s" in self.greeting:
            greeting = self.greeting%student.fname
        else:
            greeting = self.greeting
        email_msg.set_content("%s\n\n\t%s\n\n%s"%(greeting, body, self.closing))
        email_msg['Subject'] = self.subject
        email_msg['From'] = "%s <%s>"%(self.from_name, self.from_email)
        email_msg['To'] = "%s %s <%s>"%(student.fname, student.lname, student.email)
        #Attach the PDF rubric
        pdf_name = make_pdf_name(self.pdf_prefix, student)
        file_name = pdf_name[pdf_name.rfind(os.sep)+1:]
        with open(pdf_name, 'rb') as att:
            att_data = att.read()
        ctype, encoding = mimetypes.guess_type(pdf_name)
        if ctype is None or encoding is not None:
            # No guess could be made, or the file is encoded (compressed), so
            # use a generic bag-of-bits type.
            ctype = 'application/octet-stream'
        maintype, subtype = ctype.split('/', 1)
        email_msg.add_attachment(att_data, maintype=maintype, subtype=subtype, filename=file_name)
        #Attach any other attachments
        atts = set(self.attachments)
        for att in attachments:
            atts.add(att)
        for attachment in atts:
            file_name = attachment[attachment.rfind(os.sep)+1:]
            with open(attachment, 'rb') as att:
                att_data = att.read()
            ctype, encoding = mimetypes.guess_type(attachment)
            if ctype is None or encoding is not None:
                # No guess could be made, or the file is encoded (compressed), so
                # use a generic bag-of-bits type.
                ctype = 'application/octet-stream'
            maintype, subtype = ctype.split('/', 1)
            email_msg.add_attachment(att_data, maintype=maintype, subtype=subtype, filename=file_name)
        return email_msg


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
    def get_ok_students(self, only_finished = False, all = False):
        def rubric_is_ok(rubric):
            return all or rubric.is_filled() or (not only_finished and\
                rubric.is_in_progress())
        ret = set()
        for student in self.get_students():
            rubric = self.get_rubric(student)
            if rubric_is_ok(rubric):
                ret.add(student)
        return ret

    #Save all the rubrics
    def save(self, file):
        global saved
        try:
            fd = open(file, 'w')
        except FileNotFoundError:
            print("Error: File %s not found"%file)
            return
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
        #tex_files = []
        for student in self.get_students():
            rubric = self.get_rubric(student)
            if all or rubric.is_filled() or (not only_finished and\
                    rubric.is_in_progress()):
                #Include this one
                fname = make_file_name(pdf_prefix, student)
                if self.is_using_groups():
                    group = self.get_group(student)
                else:
                    group = None
                rubric.export_pdf(fname, student=student, group=group, verbose=verbose)
                #rubric.write_tex(fname, student=student, group=group)
                #tex_files.append(fname)
                #if verbose:
                #    print("%s written successfully"%fname[fname.rfind(os.sep)+1:])
        # print("\nAll .tex files written successfully\n")
        # #Now, compile all of them
        # for tex_file in tex_files:
        #     dirc = tex_file[:tex_file.rfind(os.sep)]
        #     fname = tex_file[tex_file.rfind(os.sep)+1:-4] + '.pdf'
        #     #Remove any old file, if it exists
        #     if os.path.isfile(dirc + os.sep + fname):
        #         os.remove(dirc + os.sep + fname)
        #     args_tex = ['pdflatex', '-output-directory=%s'%dirc,\
        #         '-halt-on-error','-interaction=nonstopmode', tex_file]
        #     if verbose:
        #         subprocess.run(args_tex)
        #     else:
        #         subprocess.run(args_tex, stdout=subprocess.DEVNULL)
        #     if not os.path.isfile(dirc + os.sep + fname):
        #         raise ValueError("%s failed to compile"%tex_file[tex_file.rfind(os.sep)+1:])
        #     if verbose:
        #         print("%s compiled successfully"%fname)
        if verbose:
            print()
        print("All .pdf files compiled successfully\n")

    #Send emails to students
    def email_students(self, pdf_prefix, email_manager):
        #Prepare subject
        subject = input("Email subject: ")
        #Prepare greeting
        greeting = unquote(seeded_input("Email greeting (use %s for student name): ",\
            "Dear %s,"))
        #Prepare email body
        print("Email body (to break lines, end with \\):")
        body = ""
        while True:
            body_piece = input()
            body += body_piece
            if len(body_piece) > 0 and body_piece[-1] == '\\':
                body = body[:-1]
            else:
                break
        body = unquote(body)
        #Prepare closing
        print("Email closing (e.g. your name):")
        closing = ""
        while True:
            closing_piece = input()
            closing += closing_piece
            if len(closing_piece) > 0 and closing_piece[-1] == '\\':
                closing = closing[:-1]
            else:
                break
        closing = unquote(closing)
        ##Any extra attachments?
        #atts = []
        #att_path = ""
        #while True:
        #    att_path = files_input("Extra attachment: ",
        #                                extensions = [None]).strip()
        #    #print(att_path)
        #    if att_path == '':
        #        #No attachment; done
        #        break
        #    if os.path.isfile(att_path):
        #        atts.append(att_path)
        #    else:
        #        print("Error: File not found: %s"%att_path)
        #Set the template
        email_template = EmailTemplate(message = body, closing = closing,\
            subject = subject, my_email = email_manager.get_email(),\
            my_name = email_manager.get_name(), greeting = greeting,\
            pdf_prefix = pdf_prefix)
        send_ok = True
        new_body = False
        previewed = False
        fname = None
        global_atts = set()
        def send_not_ok():
            nonlocal send_ok
            send_ok = False
        def edit_body():
            nonlocal new_body
            nonlocal body
            body = seeded_input("Edit body: ", body)
            new_body = True
        def preview_pdf():
            nonlocal previewed
            nonlocal fname
            previewed = True
            webbrowser.open_new(r'file://%s'%os.path.abspath(fname))
            print_delay("")
        def preview_attachments():
            nonlocal global_atts
            nonlocal previewed
            previewed = True
            if len(global_atts) == 0:
                print("No extra attachments to preview")
                return
            for att in global_atts:
                print("Previewing attachment: %s"%att)
                webbrowser.open_new(r'file://%s'%os.path.abspath(att))
                print_delay("")
        email_edit_menu = Menu("Action", back = False)
        email_edit_menu.add_item("Looks good!", lambda : None)
        email_edit_menu.add_item("Don't send!", send_not_ok)
        email_edit_menu.add_item("Edit body", edit_body)
        email_edit_menu.add_item("Preview PDF", preview_pdf)
        email_edit_menu.add_item("Preview Extra Attachments", preview_attachments)
        #Log into email_manager
        email_manager.login()
        #Go through students
        for student in self.get_students():
            fname = make_pdf_name(pdf_prefix, student)
            global_atts = self.get_rubric(student).get_attachments()
            if os.path.isfile(fname):
                send_ok = True
                while True:
                    #Prep email
                    if not previewed:
                        email_msg = email_template.render(student, message = body,\
                                                            attachments = global_atts)
                    #Offer to edit
                    new_body = False
                    previewed = False
                    print_email(email_msg)
                    #Proof
                    email_edit_menu.prompt()
                    if not new_body and not previewed:
                        break
                #Send
                if send_ok:
                    email_manager.send_message(email_msg)
            elif verbose:
                print("File not found: %s\nSkipping...\n"%fname)
        #Log out of email_manager
        email_manager.logout()


class ItemChangingText:
    def __init__(self, item):
        self.item = item

    def __str__(self):
        ret = self.item.get_name()
        if not self.item.has_own_field():
            if self.item.get_comment() != "":
                ret += " \"%s\""%self.item.get_comment()
        else:
            score = self.item.get_score()
            if score is None:
                ret += " (out of %d)"%(self.item.get_value())
            elif isinstance(score, int):
                ret += " (%d/%d)"%(score, self.item.get_value())
            else:
                ret += " (%.2f/%d)"%(score, self.item.get_value())
            if self.item.get_comment() != "":
                ret += " \"%s\""%self.item.get_comment()
        if self.item.is_changed():
            ret = "* " + ret
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
        self.changed = False
        self.id = Item.next_id
        Item.next_id += 1

    def set_comment(self, comment):
        global saved
        saved = False
        self.changed = True
        self.comment = comment

    def get_comment(self):
        return self.comment

    def set_score(self, score):
        global saved
        saved = False
        self.changed = True
        self.score = score

    def get_score(self):
        return self.score

    def get_value(self):
        return self.value

    def get_name(self):
        return self.name

    def __str__(self):
        ret = "%s\t%d"%(self.get_name(), self.get_value())
        score = self.get_score()
        if score is not None:
            if isinstance(score, int):
                ret += "\t%d"%score
            else:
                ret += "\t%.2f"%score
        if self.comment is not None:
            ret += "\t%s"%self.comment
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

    def is_changed(self):
        return self.changed

    def save(self):
        self.changed = False

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

    def add_items_to_menu(self, menu):
        def add_items_to_menu_action(item):
            if item.edit_menu is None:
                item.edit_menu = EditMenu(item)
            #menu.add_item(self.get_name(), self.edit_menu.prompt)
            menu.add_item(ItemChangingText(item), item.edit_menu.prompt)
        self.traverse(add_items_to_menu_action)

    #Fill in all unfilled scores with 100%
    def fill_scores(self):
        def fill_scores_action(item):
            if item.get_score() is None:
                item.set_score(item.get_value())
        self.traverse(fill_scores_action)

    #Mark this Category and all its children as saved
    def save(self):
        def action(item):
            if item != self:
                item.save()
            else:
                super().save()
        self.traverse(action, ignore_blanks = False)

    #Check for unsaved changes anywhere in the heirarchy
    def is_deep_changed(self):
        def action(item):
            return item.is_changed()
        ret = False
        def accum(add_bool):
            nonlocal ret
            ret = ret or add_bool
        self.traverse(action, accum, ignore_blanks = False)
        return ret


class FrontmatterChangingText:
    def __init__(self, fm, fm_dict):
        self.fm = fm
        self.fm_dict = fm_dict

    def __str__(self):
        if self.fm_dict[self.fm] is None:
            return self.fm
        else:
            return "%s (\"%s\")"%(self.fm, self.fm_dict[self.fm])

#Class representing a rubric
class Rubric:
    #Constructor
    def __init__(self, from_file_or_rubric, reference_student = None):
        #Menus
        self.menu = None
        self.frontmatter_menu = None
        self.auto_comment_menu = None
        self.att_menu = None
        #Flag to keep track of if this thing has been saved
        self.changed = False
        if isinstance(from_file_or_rubric, Rubric):
            #We're making a copy
            other = from_file_or_rubric
            self.frontmatter = list(other.frontmatter)
            self.frontmatter_dict = dict(other.frontmatter_dict)
            self.attachments = set(other.attachments)
            self.total = other.total.copy(reference_student)
            return
        #It's from a file
        from_file = from_file_or_rubric
        #Things that need to be manually entered (e.g. a title)
        self.frontmatter = []
        self.frontmatter_dict = dict()
        #Attachments
        self.attachments = set()
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

    #Is all the front matter set?
    def full_front_matter(self):
        for fm in self.frontmatter:
            if self.frontmatter_dict[fm] is None:
                return False
        return True

    #Is any of the front matter set?
    def some_front_matter(self):
        for fm in self.frontmatter:
            if self.frontmatter_dict[fm] is not None:
                return True
        return False

    #Is every field graded?
    def is_filled(self):
        return self.total.get_score() is not None

    #Is any field graded and/or commented?
    def is_in_progress(self):
        def checker(item):
            return item.get_score() is not None or item.get_comment() != ''
        ret = False
        def accumulator(add_bool):
            nonlocal ret
            ret = ret or add_bool
        self.total.traverse(checker, accumulator, ignore_blanks = False)
        return ret

    #Does any auto-calculated field have a comment?
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
        def modify_front_matter(label):
            global saved
            fm_text = self.frontmatter_dict[label]
            if fm_text is None:
                fm_text = ""
            try:
                val = seeded_input("Enter value for \"%s\", or CTRL+C to cancel: "\
                    %label, fm_text)
            except KeyboardInterrupt:
                print("\nCanceled\n")
                return
            else:
                saved = False
                self.changed = True
                self.frontmatter_dict[label] = val
        if len(self.frontmatter) == 1:
            modify_front_matter(self.frontmatter[0])
            return
        elif self.frontmatter_menu is None:
            self.frontmatter_menu = Menu("Select item:", menued = False)
            for fm in self.frontmatter:
                self.frontmatter_menu.add_item(FrontmatterChangingText(fm,\
                    self.frontmatter_dict), modify_front_matter, fm)
        self.frontmatter_menu.prompt()

    #Add a comment to a category with no field for itself
    def add_auto_comment(self):
        if self.auto_comment_menu is None:
            self.auto_comment_menu = Menu("Select category to add comment to:", menued = False)
            def auto_comment(item):
                global saved
                old_comment = item.get_comment()
                try:
                    comment = seeded_input("Enter comment for %s, or CTRL+C to cancel: "\
                        %item.get_name(), old_comment)
                except KeyboardInterrupt:
                    print("\nCanceled")
                    return
                self.changed = True
                saved = False
                item.set_comment(comment)
            def traverser(item):
                if not item.has_own_field():
                    return self.auto_comment_menu.add_item(ItemChangingText(item),\
                        auto_comment, item)
            self.total.traverse(traverser, ignore_blanks = False)
        self.auto_comment_menu.prompt()

    def remove_attachment(self, att):
        global saved
        self.attachments.remove(att)
        saved = False
        self.changed = True

    def add_attachment(self, att):
        global saved
        if os.path.isfile(att):
            self.attachments.add(att)
        else:
            print("Error: File not found: %s"%att)
            return
        saved = False
        self.changed = True

    #Get attachments
    def get_attachments(self):
        return set(self.attachments)

    #Manage attachments
    def manage_attachments(self):
        self.att_menu = Menu("Select option:", menued = False)
        def add_attachment():
            try:
                att = files_input("Filename to attach, or CTRL+C to cancel: ",
                                            extensions = [None])
            except KeyboardInterrupt:
                print("\nCanceled\n")
                return
            else:
                self.add_attachment(att)
        self.att_menu.add_item("New Attachment", add_attachment)
        for att in self.attachments:
            self.att_menu.add_item("Delete %s"%att, self.remove_attachment, att)
        self.att_menu.prompt()


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
        #Add attachments to the thing
        self.menu.add_item("Manage attachments", self.manage_attachments)
        self.menu.add_item("Set rest to 100%", self.total.fill_scores)
        return self.menu

    def grade(self):
        #return self.get_menu().prompt()
        MenuManager.get_menu_manager().add_menu(self.get_menu())

    #Mark everything as not changed
    def save(self):
        self.changed = False
        self.total.save()

    def is_changed(self):
        return self.changed or self.total.is_deep_changed()

    #Convert to a string that can be imported
    def export_rubric(self):
        def transcriber(item):
            score = item.get_score()
            if item.has_own_field() and (score is not None or item.get_comment() != ''):
                if item.get_individual() is not None:
                    if score is not None:
                        if isinstance(score, int):
                            return "%d%s%s%s%d%s%s\n"%(item.get_id(), RUBRIC_SAVE_SEPARATOR,\
                                str(item.get_individual()), RUBRIC_SAVE_SEPARATOR,\
                                score, RUBRIC_SAVE_SEPARATOR, item.get_comment())
                        else:
                            return "%d%s%s%s%.2f%s%s\n"%(item.get_id(), RUBRIC_SAVE_SEPARATOR,\
                                str(item.get_individual()), RUBRIC_SAVE_SEPARATOR,\
                                score, RUBRIC_SAVE_SEPARATOR, item.get_comment())
                    else:
                        return "%d%s%s%s%s%s\n"%(item.get_id(), RUBRIC_SAVE_SEPARATOR,\
                            str(item.get_individual()), RUBRIC_SAVE_SEPARATOR,\
                            RUBRIC_SAVE_SEPARATOR, item.get_comment())
                else:
                    if score is not None:
                        if isinstance(score, int):
                            return "%d%s%d%s%s\n"%(item.get_id(), RUBRIC_SAVE_SEPARATOR,\
                                score, RUBRIC_SAVE_SEPARATOR, item.get_comment())
                        else:
                            return "%d%s%.2f%s%s\n"%(item.get_id(), RUBRIC_SAVE_SEPARATOR,\
                                score, RUBRIC_SAVE_SEPARATOR, item.get_comment())
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
        #Add on attachments
        for att in self.attachments:
            ret += '%s%s\n'%(RUBRIC_ATTACHMENT_INDICATOR, att)
        self.save()
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
            elif line_pieces[0][0] == RUBRIC_ATTACHMENT_INDICATOR:
                #Attachment
                self.attachments.add(line_pieces[0][1:])
                continue
            the_id = int(line_pieces[0])
            if len(line_pieces[1]) > 0 and not is_number(line_pieces[1]):
                #We have an individualized thing
                individual_str = line_pieces[1]
                del line_pieces[1]
            else:
                individual_str = None
            the_score = line_pieces[1]
            if the_score == '':
                the_score = None
            elif the_score.find('.') >= 0:
                the_score = float(the_score)
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
        self.save()

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
                score = item.get_score()
                if score is None:
                    return ""
                elif isinstance(score, int):
                    return str(score)
                else:
                    return "%.2f"%score
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
            elif isinstance(score, int):
                score = str(score)
            else:
                score = "%.2f"%score
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

    #Write a .tex file for this rubric
    def write_tex(self, fname, student=None, group=None, header=None):
        with open(fname, 'w') as fd:
            fd.write("\\documentclass[%dpt]{article}\n"%TEX_FONT_SIZE)
            fd.write("\\usepackage[T1]{fontenc}\n")
            fd.write("\\usepackage{fullpage}\n")
            fd.write("\\usepackage[none]{hyphenat}\n")
            fd.write("\\usepackage{array}\n")
            fd.write("\\usepackage{longtable}\n")
            fd.write("\\pagenumbering{gobble}\n")
            fd.write("\\begin{document}\n\\noindent ")
            if student is None:
                fd.write("\\textbf{%s}\\\\\n"%header)
            elif group is None:
                fd.write("\\textbf{%s %s}\\\\\n"%(student.fname, student.lname))
                fd.write(self.get_front_matter_tex())
            else:
                fd.write("\\textbf{Group %d}\\\\\n"%group.number)
                fd.write(self.get_front_matter_tex())
                fd.write("\\textbf{Members:} %s\\\\\n"%', '.join(\
                    ['%s %s'%(s.fname, s.lname) for s in group]))
                fd.write("\\textbf{Graded Member:} %s %s\\\\\n"%\
                    (student.fname, student.lname))

            fd.write("\n\\noindent\\begin{longtable}{|>{\\raggedright}p{1.7in}|l|l|>{\\raggedright\\arraybackslash}p{2.8in}|}\\hline\n")
            fd.write("&\\textbf{TOTAL}&\\textbf{POINTS}&\\textbf{COMMENTS}\\\\\\hline\n\\endhead\n")
            fd.write(self.get_tex())
            fd.write("\\end{longtable}\n")
            fd.write("\\end{document}")

    #Write a pdf for this rubric
    def export_pdf(self, fname, student=None, group=None, verbose=False, header=None):
        #Write the .tex file
        tex_fname = "%s.tex"%fname
        self.write_tex(tex_fname, student=student, group=group, header=header)
        if verbose:
            print("\n%s written successfully"%tex_fname[tex_fname.rfind(os.sep)+1:])
        #print("\nAll .tex files written successfully\n")
        #Now, compile it
        dirc = fname[:fname.rfind(os.sep)]
        pdf_fname = fname[fname.rfind(os.sep)+1:] + '.pdf'
        #Remove any old file, if it exists
        if os.path.isfile(dirc + os.sep + pdf_fname):
            os.remove(dirc + os.sep + pdf_fname)
        args_tex = ['pdflatex', '-output-directory=%s'%dirc,\
            '-halt-on-error','-interaction=nonstopmode', tex_fname]
        if verbose:
            subprocess.run(args_tex)
        else:
            subprocess.run(args_tex, stdout=subprocess.DEVNULL)
        if not os.path.isfile(dirc + os.sep + pdf_fname):
            raise ValueError("%s failed to compile"%tex_fname[tex_fname.rfind(os.sep)+1:])
        if verbose:
            print("\n%s compiled successfully"%pdf_fname)
        # if verbose:
        #     print()
        # print("All .pdf files compiled successfully\n")

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
    msg = "Enter grade, blank to clear, or CTRL+C to cancel: "
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
            #print(item.is_changed())
    except KeyboardInterrupt:
        print("\nCanceled")
    except ValueError:
        print("\nError: Cannot parse grade. Canceling...")

def assign_comment(item):
    score = item.get_score()
    if score is not None:
        if isinstance(score, int):
            print("Comment for %s, score of %d/%d"%(item.get_name(),\
                score, item.get_value()))
        else:
            print("Comment for %s, score of %.2f/%d"%(item.get_name(),\
                score, item.get_value()))
    else:
        print("Comment for %s, score TBD"%item.get_name())
    msg = "Please enter comment, or CTRL+C to cancel: "
    old_comment = item.get_comment()
    try:
        comment = seeded_input(msg, old_comment)
    except KeyboardInterrupt:
        print("\nCanceled")
        return
    item.set_comment(comment)

class ChangingText:
    def __init__(self, text1, text2, conditional, *args):
        self.text1 = text1
        self.text2 = text2
        self.conditional = conditional
        self.args = args

    def __str__(self):
        if self.conditional(*self.args):
            if isinstance(self.text1, collections.abc.Callable):
                return self.text1(*self.args)
            else:
                return self.text1
        else:
            if isinstance(self.text2, collections.abc.Callable):
                return self.text2(*self.args)
            else:
                return self.text2

class EditMenu(Menu):
    def __init__(self, grade_item):
        def score_to_string(score):
            if isinstance(score, int):
                return "%d"%score
            else:
                return "%.2f"%score
        super().__init__("Action on %s:"%grade_item.get_name(), menued = False)
        self.add_item(ChangingText("Grade", lambda item:\
            "Update Grade (%s/%d)"%(score_to_string(item.get_score()), item.get_value()),\
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
        def grade_and_comment(itm):
            assign_grade(itm)
            if itm.get_score() is not None:
                assign_comment(itm)
        self.add_item("Both", grade_and_comment, grade_item)

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
            exister_output = exister(self.directory, fil)
            #print(exister_output)
            if isinstance(exister_output, str):
                exists = os.path.isfile(exister_output)
            else:
                exists = False
                for potential_file in exister_output:
                    if os.path.isfile(potential_file):
                        exists = True
                        break
            #print(exists)
            #print(os.path.isfile("100-test/test.csv"))
            if exists:
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

    def get_save_file(self, save_as = False, extension = ""):
        def the_exister(a, s):
            if len(extension) == 0 or s[-len(extension):] == extension:
                return a + s
            else:
                return a + s + extension
        return self.get_cond_file("File to save into: ", FileManager.FILE_KEY,\
            save_as = save_as, exister = the_exister)

    def get_open_file(self):
        fil = files_input("File to open: ", self.directory)
        if not os.path.isfile(self.directory + fil):
            raise FileNotFoundError("File %s not found"%fil)
        self.files[FileManager.FILE_KEY] = fil
        return self.directory + self.files[FileManager.FILE_KEY]

    def get_export_file(self, save_as = False):
        return self.get_cond_file("File to export into: ", FileManager.CSV_KEY,\
            save_as = save_as)

    def get_pdf_prefix(self, students = set(), save_as = False):
        def the_exister(a, s):
            if s is None:
                return '.'
            else:
                ret = set()
                for student in students:
                    ret.add(a + make_tex_name(s, student))
                return ret
        return self.get_cond_file("PDF prefix to use: ", FileManager.PDF_KEY,\
            exister = the_exister,\
            confirmer = "Warning: Prefix %s already in use. Overwrite?")
            #, returner = lambda a, s: s, save_as = save_as)

    def get_open_pdf_prefix(self):
        return self.get_cond_file("PDF prefix to use: ", FileManager.PDF_KEY,\
            exister = lambda a, s: '.',\
            confirmer = "Warning: Prefix %s already in use. Overwrite?")

#Class for error for exiting email early
class EmailManagerCanceled(Exception):
    def __init__(self, msg):
        super().__init__(msg)

#Class for managing email stuff
class EmailManager:
    dummy_mode = 'Dummy'
    known_modes = {
        'Gmail':['imap.gmail.com', 'SSL', 'smtp.gmail.com', 'SSL', 'Sent'],
        'Microsoft':['outlook.office365.com', 'SSL', 'smtp.office365.com',\
            'STARTTLS', 'Sent Items']
    }
    def __init__(self, from_file = None, special_mode = None, verbose = False):
        def get_out():
            raise EmailManagerCanceled("Canceled Email Setup")
        def get_out_prompt(menu):
            try:
                menu.prompt()
            except KeyboardInterrupt:
                get_out()
        ok = False
        the_file = from_file
        self.name = ""
        self.email = ""
        self.imap = ""
        self.smtp = ""
        self.sent_folder = "Sent"
        self.verbose = verbose
        self.imap_server = None
        self.smtp_server = None
        self.dummy = False
        while not ok:
            if special_mode == EmailManager.dummy_mode:
                self.dummy = True
                print("Dummy email manager created successfully")
                return
            elif the_file is None:
                #Enter the info
                #Name
                self.name = seeded_input("Enter your name: ", self.name)
                #Email address
                self.email = seeded_input("Enter your email address: ", self.email)
                if special_mode in EmailManager.known_modes:
                    #Gmail or Microsoft
                    self.imap = EmailManager.known_modes[special_mode][0]
                    self.imap_auth = EmailManager.known_modes[special_mode][1]
                    self.smtp = EmailManager.known_modes[special_mode][2]
                    self.smtp_auth = EmailManager.known_modes[special_mode][3]
                    self.sent_folder = EmailManager.known_modes[special_mode][4]
                else:
                    #IMAP server
                    self.imap = seeded_input("IMAP server: ", self.imap)
                    #IMAP server authentication mode
                    cur_serv = "IMAP"
                    def set_auth(value):
                        if cur_serv == "IMAP":
                            self.imap_auth = value
                        else:
                            self.smtp_auth = value
                    auth_menu = Menu("Authentication Mode:", back = False)
                    for mode in ["None", "SSL", "STARTTLS"]:
                        auth_menu.add_item(mode, set_auth, mode)
                    get_out_prompt(auth_menu)
                    #SMTP server
                    self.smtp = seeded_input("SMTP server: ", self.smtp)
                    #SMTP server authentication mode
                    cur_serv = "SMTP"
                    get_out_prompt(auth_menu)
                    #Sent folder
                    self.sent_folder = seeded_input("Name of Sent folder: ",\
                        self.sent_folder)
            else:
                #Read from config file
                with open(from_file, 'r') as fd:
                    lines = []
                    for line in fd:
                        lstrip = line.strip()
                        if len(lstrip) > 0 and lstrip[0] != EMAIL_CONFIG_COMMENT:
                            lines.append(lstrip)

                    if lines[0] in EmailManager.known_modes:
                        #First line is Gmail or Microsoft
                        self.name = lines[1]
                        self.email = lines[2]
                    else:
                        self.name = lines[0]
                        self.email = lines[1]
                        self.imap = lines[2]
                        self.imap_auth = lines[3]
                        self.smtp = lines[4]
                        self.smtp_auth = lines[5]
                        self.sent_folder = lines[6]

            #Verify all the info
            ok = True
            def not_ok():
                nonlocal ok
                nonlocal the_file
                ok = False
                the_file = None
            print()
            print("Name: %s"%self.name)
            print("Email: %s"%self.email)
            print("IMAP: %s, Auth = %s"%(self.imap, self.imap_auth))
            print("SMTP: %s, Auth = %s"%(self.smtp, self.smtp_auth))
            print("Sent folder: %s"%self.sent_folder)
            print()
            ok_menu = Menu("Everything look ok?", back = False)
            ok_menu.add_item("Yes", lambda : None)
            ok_menu.add_item("No", not_ok)
            ok_menu.add_item("Cancel", get_out)
            get_out_prompt(ok_menu)

        ok = False
        sent_changed = False
        while not ok:
            try:
                if not sent_changed:
                    self.password = getpass.getpass("Password for %s: "%self.email)
                ok = True
                sent_changed = False
                #Try logging into IMAP server
                try:
                    self.imap_login()
                    try:
                        self.smtp_login()
                    except smtplib.SMTPException:
                        ok = False
                        print_delay("\nError logging into SMTP server\n")
                    print("\nLogin succesful!\n")
                except ValueError:
                    ok = False
                    print_delay("\nInvalid Sent folder\n")
                    self.sent_folder = seeded_input("Please enter new Sent folder: ",\
                        self.sent_folder)
                    sent_changed = True
                except imaplib.IMAP4.error:
                    ok = False
                    print_delay("\nError logging into IMAP server\n")
            except KeyboardInterrupt:
                get_out()

        if the_file is None:
            save_config_menu = Menu("Would you like to save these settings in a config file?",\
                back = False)
            def save_email_config(the_fname = None):
                fname = the_fname
                if fname is None:
                    fname = input("Filename to save config file: ")
                    if os.path.isfile(fname):
                        overwrite_warning_menu = Menu("Warning: file %s already exists. Overwrite?"\
                            %fname, back = False)
                        overwrite_warning_menu.add_item("Enter New Name", save_email_config)
                        overwrite_warning_menu.add_item("Overwrite", save_email_config, fname)
                        overwrite_warning_menu.add_item("Cancel", lambda : None)
                        overwrite_warning_menu.prompt()
                        raise EmailManagerCanceled("Entered existing filename")
                with open(fname, 'w') as cfd:
                    for item in [self.name, self.email, self.imap,\
                            self.imap_auth, self.smtp, self.smtp_auth,\
                            self.sent_folder]:
                        cfd.write("%s\n"%item)
            save_config_menu.add_item("No", lambda : None)
            save_config_menu.add_item("Yes", save_email_config)
            try:
                save_config_menu.prompt()
            except EmailManagerCanceled:
                pass

    #Get your name
    def get_name(self):
        return self.name

    #Get your email address
    def get_email(self):
        return self.email

    #Log into both servers
    def login(self):
        self.imap_login()
        self.smtp_login()

    #Log out from both servers
    def logout(self):
        self.imap_logout()
        self.smtp_logout()

    #Log into IMAP server
    def imap_login(self):
        if self.dummy:
            if self.verbose:
                print("Dummy: imap login")
            return
        if self.imap_server is not None:
            # #Log out first if already logged in
            # self.imap_logout()
            #Do nothing
            if self.verbose:
                print("IMAP: Already logged in")
            return
        #Initialize/Authenticate
        if self.imap_auth == 'SSL':
            self.imap_server = imaplib.IMAP4_SSL(host=self.imap)
        else:
            self.imap_server = imaplib.IMAP4(host=self.imap)
            if self.imap_auth == 'STARTTLS':
                self.imap_server.starttls()
        if self.verbose:
            print("Logging into IMAP...")
        #Log in to server
        try:
            self.imap_server.login(self.email, self.password)
            if self.verbose:
                print("Logged in!\n")
            #Select the sent folder
            sel = self.imap_server.select('"%s"'%self.sent_folder)
            if sel[0] != 'OK':
                raise ValueError("Invalid Sent folder: %s"%str(sel))
            elif verbose:
                print("Selected Sent folder: %s"%self.sent_folder)
            val = sel[1][0]
            self.message_count_init = int(val)
            if verbose:
                print("%d messages in %s\n"%(self.message_count_init, self.sent_folder))
        except:
            self.imap_server = None
            raise

    #Log into SMTP server
    def smtp_login(self):
        if self.dummy:
            if self.verbose:
                print("Dummy: smtp login")
            return
        if self.smtp_server is not None:
            # #Log out first if already logged in
            # self.smtp_logout()
            #Do nothing
            if self.verbose:
                print("SMTP: Already logged in")
            return
        #Initialize/Authenticate
        if self.smtp_auth == 'SSL':
            self.smtp_server = smtplib.SMTP_SSL(host=self.smtp)
        else:
            self.smtp_server = smtplib.SMTP(host=self.smtp)
            if self.smtp_auth == 'STARTTLS':
                self.smtp_server.starttls()
        if self.verbose:
            print("Logging into SMTP...")
        #Log in to server
        try:
            self.smtp_server.login(self.email, self.password)
            if self.verbose:
                print("Logged in!\n")
        except:
            self.smtp_server = None
            raise

    #Log out from IMAP server
    def imap_logout(self):
        if self.dummy:
            if self.verbose:
                print("Dummy: imap logout")
            return
        if self.imap_server is not None:
            if self.verbose:
                print("Logging out of IMAP server...")
            self.imap_server.logout()
            self.imap_server = None

    #Log out from SMTP server
    def smtp_logout(self):
        if self.dummy:
            if verbose:
                print("Dummy: smtp logout")
            return
        if self.smtp_server is not None:
            if self.verbose:
                print("Logging out of SMTP server...")
            try:
                self.smtp_server.quit()
            except smtplib.SMTPServerDisconnected:
                print("SMTP server disconnected on its own")
                print()
            self.smtp_server = None

    #Send the email message
    #Store a copy in the sent folder
    def send_message(self, email_msg):
        if self.dummy:
            if self.verbose:
                print("Dummy: send message")
            return
        #IMAP stuff
        #Copy the message
        date = imaplib.Time2Internaldate(time.time())
        app = self.imap_server.append('"%s"'%self.sent_folder, None, date, bytes(email_msg))
        if app[0] != 'OK':
            raise ValueError("Copying to %s failed: %s"%(self.sent_folder, str(app)))
        if verbose:
            print("Message copied to %s"%self.sent_folder)
        #Mark it as read
        try:
            srch = self.imap_server.search(None, '(UNSEEN)')
            if srch[0] != 'OK':
                raise(ValueError("Search for unread messages failed: %s"%str(srch)))
            for msg in srch[1]:
                try:
                    if int(msg) >= self.message_count_init:
                        stor = self.imap_server.store(msg, '+FLAGS', '\\Seen')
                        if stor[0] != 'OK':
                            raise(ValueError("Failed to mark message as read: %s"%str(stor)))
                    elif verbose:
                        print(int(msg), srch)
                        print("Message marked as read")
                except ValueError:
                    raise(ValueError("Failed to mark message as read, weird error: %s"%str(msg)))
        except ValueError as er:
            print("Message NOT marked as read")
            print("Exception: ")
            print(er)
            print()

        #SMTP stuff
        self.smtp_server.send_message(email_msg)
        print("Message sent")

    #Is this manager a dummy?
    def is_dummy(self):
        return self.dummy

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

    if verbose and libedit:
        print("Warning: Using libedit readline. Some advanced features may work suboptimally.\n")

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
        try:
            fil = file_manager.get_save_file(save_as)
        except KeyboardInterrupt:
            fil = None
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
        except KeyboardInterrupt:
            return
        try:
            roster.load(fil)
        except KeyError:
            print("Invalid file; failed to load")
            print()

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
            the_rubric = roster.get_rubric(self.entity)
            if the_rubric.is_filled():
                #ret = '(done) ' + ret
                tack = 'done'
            elif the_rubric.is_in_progress() or\
                    the_rubric.some_front_matter():
                #ret = '(in progress) ' + ret
                tack = 'in progress'
            if tack is not None:
                if not the_rubric.full_front_matter():
                    tack += '*'
                ret = '(%s) '%tack + ret
            if the_rubric.is_changed():
                ret = '* ' + ret
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
        try:
            fil = file_manager.get_export_file(save_as)
        except KeyboardInterrupt:
            fil = None
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
        try:
            fil = file_manager.get_pdf_prefix(roster.get_ok_students(only_finished =\
                flag == pdf_flag_list[0], all = flag == pdf_flag_list[-1]),\
                pdf_save_as)
        except KeyboardInterrupt:
            fil = None
        if fil is not None:
            try:
                roster.export_pdfs(fil, only_finished = flag == pdf_flag_list[0],\
                    all = flag == pdf_flag_list[-1], verbose = verbose)
            except Exception as e:
                print("Fatal error occurred; not all PDFs written")
                print("Exception: ")
                print(e)
                print()
    for flag in pdf_flag_list:
        pdf_menu.add_item(flag, export_pdf, flag)
    def prompt_pdf(save_as):
        global pdf_save_as
        pdf_save_as = save_as
        pdf_menu.prompt()
    main_menu.add_item("Export PDFs", prompt_pdf, False)
    main_menu.add_item("Export PDFs as", prompt_pdf, True)
    def export_blank_pdf():
        try:
            hdr = unquote(seeded_input("What should it say at the top? ", "Rubric"),\
                latexify=True)
            fil = file_manager.get_save_file(save_as=True, extension='.pdf')
            if fil is not None and len(fil) >= 4 and fil[-4:] == '.pdf':
                fil = fil[:-4]
        except KeyboardInterrupt:
            fil = None
        if fil is not None:
            rubric.export_pdf(fil, verbose = verbose, header = hdr)
    main_menu.add_item("Export blank PDF", export_blank_pdf)

    email_manager = None
    if roster.get_students()[0].has_email():
        manager_setup_menu = Menu("How to get email data?", back = False)
        email_config_file = False
        email_mode = None
        def set_email_config_file(val):
            global email_config_file
            global email_mode
            if val == True:
                try:
                    email_config_file = files_input("Enter email config file: ").strip()
                except KeyboardInterrupt:
                    email_config_file = 0
                    print()
            else:
                email_config_file = None
                if isinstance(val, str):
                    email_mode = val
        def get_out_here():
            raise EmailManagerCanceled("canceled")
        manager_setup_menu.add_item("Back", get_out_here)
        manager_setup_menu.add_item("Enter manually", set_email_config_file, 0)
        manager_setup_menu.add_item("From config file", set_email_config_file,\
            True)
        manager_setup_menu.add_item("Manual Gmail", set_email_config_file,\
            'Gmail')
        manager_setup_menu.add_item("Manual Microsoft", set_email_config_file,\
            'Microsoft')
        manager_setup_menu.add_item("Use Dummy (for testing)", set_email_config_file,\
            EmailManager.dummy_mode)
        #Supports email
        def email_students():
            global email_manager
            global email_config_file
            try:
                if email_manager is None or email_manager.is_dummy():
                    while True:
                        manager_setup_menu.prompt()
                        if email_config_file != 0:
                            break
                        else:
                            email_config_file = None
                    email_manager = EmailManager(from_file = email_config_file,\
                        verbose = verbose, special_mode = email_mode)
                try:
                    prefix = file_manager.get_open_pdf_prefix()
                    roster.email_students(prefix, email_manager)
                except KeyboardInterrupt:
                    print("\nEmailing canceled\n")
            except EmailManagerCanceled:
                print("\nEmail Setup Canceled")
            except FileNotFoundError:
                print("\nFile %s not found\nEmail Setup Canceled"%email_config_file)
            except KeyboardInterrupt:
                print("\nEmail Setup Canceled")
        main_menu.add_item("Email PDFs", email_students)

    menu_manager.add_menu(main_menu)
    try:
        menu_manager.mainloop()
    except:
        #do cleanup
        if email_manager is not None:
            email_manager.logout()
        #print("Interrupted")
        raise
