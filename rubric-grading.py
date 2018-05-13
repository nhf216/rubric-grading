import sys
import re
import readline

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
        return "Group %d (%s)"%(self.number, ', '.join([str(s) for s in self.students]))
    
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
                    return self.rubrics[group]
        else:
            return self.rubrics[entity]

#Class representing a grading item
class Item:
    def __init__(self, name, value):
        self.name = name
        self.value = value
        self.score = None
        self.comment = ""
        self.edit_menu = None
    
    def set_comment(self, comment):
        self.comment = comment
    
    def get_comment(self):
        return self.comment
    
    def set_score(self, score):
        self.score = score
    
    def get_score(self):
        return self.score
    
    def get_value(self):
        return self.value
    
    def get_name(self):
        return self.name
    
    def __str__(self):
        ret = "%-20s%-3d"%(self.name, self.get_value())
        if self.get_score() is not None:
            ret += "%-3d"%self.get_score()
        if self.comment is not None:
            ret += "%s"%self.comment
        return ret
    
    def copy(self):
        new_item = Item(self.name, self.value)
        new_item.score = self.score
        new_item.comment = self.comment
        return new_item
    
    def is_individual(self):
        return False
    
    def individualize(self, group):
        pass
    
    def add_items_to_menu(self, menu):
        if self.edit_menu is None:
            self.edit_menu = EditMenu(self)
        menu.add_item(self.get_name(), self.edit_menu.prompt)

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
    
    def individualize(self, group):
        if self.is_individual():
            #Need to alter this
            for student in group:
                print(student)
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
    
    def deep_str(self):
        ret = str(self)
        for item in self:
            if isinstance(item, Category):
                ret += "\n%s"%item.deep_str()
            else:
                ret += "\n%s"%str(item)
        return ret + '\n'
    
    def copy(self):
        new_cat = Category(self.name, self.value, self.respect_groups)
        new_cat.score = self.score
        new_cat.comment = self.comment
        new_cat.children = dict()
        #for key in self.children:
        #    new_cat.children[key] = self.children[key].copy()
        new_cat.individual = self.individual
        for item in self:
            new_cat.add_item(item.copy())
        return new_cat
    
    def add_items_to_menu(self, menu):
        #print("hello")
        #print(self)
        if len(self.children) > 0:
            #print("has children")
            #print(self.children)
            for child in self.children.values():
                child.add_items_to_menu(menu)
        elif self.has_own_field():
            #print("entering super")
            super().add_items_to_menu(menu)
            #print("leaving super")
        for item in self:
            item.add_items_to_menu(menu)
        #print("Done with ", self)
        #print()

#Class representing a rubric
class Rubric:
    #Constructor
    def __init__(self, from_file_or_rubric):
        #Menu
        self.menu = None
        if isinstance(from_file_or_rubric, Rubric):
            #We're making a copy
            other = from_file_or_rubric
            self.frontmatter = list(other.frontmatter)
            self.total = other.total.copy()
            return
        #It's from a file
        from_file = from_file_or_rubric
        #Things that need to be manually entered (e.g. a title)
        self.frontmatter = []
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
        return self.total.deep_str()
    
    #If graded_entity is a FrozenGroup, find all non-group-respecting Categories
    #and replace them with one per individual
    #If graded_entity is a Student, do nothing
    def individualize(self, graded_entity):
        if isinstance(graded_entity, FrozenGroup):
            self.total.individualize(graded_entity)
    
    def is_filled(self):
        return self.total.get_score() is not None
    
    #Build a menu out of this rubric
    def get_menu(self):
        if self.menu is not None:
            return self.menu
        self.menu = Menu("Select an item/category:")
        self.total.add_items_to_menu(self.menu)
        return self.menu
    
    def grade(self):
        return self.get_menu().prompt()

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
    def __init__(self, message, min_item = 0, back = True):
        self.message = message
        self.items = []
        self.min_item = min_item
        if back:
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
                chosen_item = int(ipt)
                if chosen_item < self.min_item:
                    raise ValueError("Value entered too small: %d"%chosen_item)
                elif chosen_item >= len(self.items) + self.min_item:
                    raise ValueError("Value entered too large: %d"%chosen_item)
                else:
                    return self.items[chosen_item - self.min_item].evoke()
            except ValueError as err:
                print(err)
                print("Try Again\n")
    
    #Add an item to this menu
    def add_item(self, text, callback, *args):
        self.items.append(MenuItem(text, callback, *args))

def assign_grade(item):
    print("Grading %s, out of %d"%(item.get_name(), item.get_value()))
    msg = "Please enter grade, or a non-number to cancel: "
    try:
        grade = input(msg)
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
    comment = input(msg)
    if comment == '0':
        print("Canceled")
    else:
        item.set_comment(comment)

def function_sequencer(funcs, *args):
    for func in funcs:
        func(*args)

class EditMenu(Menu):
    def __init__(self, grade_item):
        super().__init__("Action on %s:"%grade_item.get_name())
        grade_str = "Grade"
        if grade_item.get_score() is not None:
            grade_str = "Update Grade"
        self.add_item(grade_str, assign_grade, grade_item)
        comment_str = "Comment"
        if grade_item.get_comment() != "":
            comment_str = "Update Comment"
        self.add_item(comment_str, assign_comment, grade_item)
        self.add_item("Both", function_sequencer,\
            [assign_grade, assign_comment], grade_item)



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
    
    #Build the menu
    main_menu = Menu("What would you like to do?", back = False)
    main_menu.add_item("Quit", sys.exit, 0)
    main_menu.add_item("Display Roster", print, roster)
    main_menu.add_item("Display Rubric", print, rubric)
    #Menu for viewing student rubrics
    student_menu = Menu("Select a student:")
    def print_rubric(entity):
        print(roster.get_rubric(entity))
    for student in roster.get_students():
        student_menu.add_item(student, print_rubric, student)
    main_menu.add_item("View Rubric by Student", student_menu.prompt)
    #Class used to update menu text when things are graded
    class MenuEntityTextUpdater:
        def __init__(self, entity):
            self.entity = entity
        
        def __str__(self):
            ret = str(self.entity)
            if roster.get_rubric(self.entity).is_filled():
                ret = '(done) ' + ret
            return ret
    if roster.is_using_groups():
        #Menu for viewing group rubrics
        group_menu = Menu("Select a group:")
        for group in roster:
            group_menu.add_item(group, print_rubric, group)
        main_menu.add_item("View Rubric by Group", group_menu.prompt)
        #Menu for editing rubrics
        grade_menu = Menu("Select a group:")
        for group in roster:
            grade_menu.add_item(MenuEntityTextUpdater(group),\
                roster.get_rubric(group).grade)
        main_menu.add_item("Grade a group", grade_menu.prompt)
    else:
        #Menu for editing rubrics
        grade_menu = Menu("Select a student:")
        for student in roster:
            grade_menu.add_item(MenuEntityTextUpdater(student),\
                roster.get_rubric(student).grade)
        main_menu.add_item("Grade a student", grade_menu.prompt)
    
    while True:
        main_menu.prompt()