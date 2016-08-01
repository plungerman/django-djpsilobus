from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.template import RequestContext
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response
from django.core.urlresolvers import reverse_lazy
from django.views.decorators.csrf import csrf_exempt

from djpsilobus.core.dspace import Manager, Search
from djpsilobus.core.utils import create_item

from djzbar.decorators.auth import portal_auth_required
from djzbar.utils.informix import do_sql as do_esql
from djzbar.utils.hr import chair_departments, department, department_faculty
from djzbar.utils.academics import sections
from djzbar.core.sql import ACADEMIC_DEPARTMENTS
from djzbar.constants import TERM_LIST

from djtools.fields.helpers import handle_uploaded_file

from os.path import join
from collections import OrderedDict

import re
import os
import csv
import json
import magic
import logging
import tarfile

logger = logging.getLogger(__name__)
# constants for now
YEAR = "2016"
SESS = "RA"
# alternative title meta tag for searching for files
TITLE_ALT = settings.DSPACE_TITLE_ALT

@portal_auth_required(
    session_var="DSPILOBUS_AUTH", redirect_url=reverse_lazy("access_denied")
)
def home(request, dept=None):
    # current user
    user = request.user
    uid = user.id
    # administrative users
    admin = False
    # dean or department chair
    dean_chair = None
    # faculty ID, name, courses
    fid = None
    pfid = None # post faculty ID
    faculty_name = None
    courses = None
    # fetch our departments
    if uid in settings.ADMINISTRATORS:
        admin = True
        objs = do_esql(ACADEMIC_DEPARTMENTS)
        depts = OrderedDict()
        for o in objs:
            depts[(o.dept_code)] = {
                "dept_name":o.dept_name, "dept_code":o.dept_code
            }
        depts = {"depts":depts}
    else:
        depts, dean_chair, division_name, division_code = chair_departments(uid)

    dept_list = []
    if admin or depts.get("depts"):
        for c,v in depts["depts"].iteritems():
            faculty = department_faculty(c,YEAR)
            dept_list.append({"dept_name":v,"dept_code":c,"faculty":faculty})
    else:
        # we have a faculty
        fid =  uid


    # obtain the courses for department or faculty
    if dept:
        # all faculty courses for department
        courses = sections(code=dept,year=YEAR,sess=SESS)
        dept = department(dept)
        if dept:
            dept = dept[0]
    elif request.method == "POST" and not request.FILES:
        substr = "dept_faculty"
        for key,val in request.POST.iteritems():
            if substr in key and val:
                pfid = int(val)
        if pfid:
            fid = pfid
    if fid:
        # one faculty
        courses = sections(year=YEAR,sess=SESS,fid=fid)
        if courses:
            faculty_name = courses[0][11]

    secciones = []
    if courses:
        for c in courses:
            lastname = re.sub('[^0-9a-zA-Z]+', '_', c.lastname)
            firstname = re.sub('[^0-9a-zA-Z]+', '_', c.firstname)
            phile = "{}_{}_{}_{}_{}_{}_syllabus".format(
                YEAR, SESS, c.crs_no.replace(" ","_"), c.sec_no,
                lastname, firstname
            )
            secciones.append({"obj":c,"phile":phile})


    # file upload
    phile = None
    if request.method=='POST' and request.FILES:
        # complete path to directory in which we will store the file

        syllabi = request.FILES.getlist('syllabi[]')
        # POST does not include empty file fields in [] so we use this
        # hidden field and javascript event to track
        syllabih = request.POST.getlist('syllabih[]')
        h = len(syllabi)
        for i in range (0,len(syllabih)):
            if syllabih[i] == "True":
                crs_no = request.POST.getlist('crs_no[]')[i]
                dept = department(crs_no.split(" ")[0])
                sendero = join(
                    settings.UPLOADS_DIR, YEAR, SESS, dept.hrdiv, dept.hrdept
                )
                # for display at UI level
                dept = None
                syllabus = syllabi[len(syllabi)-h]
                # must be after the above
                h -= 1
                crs_title = request.POST.getlist('crs_title[]')[i]
                filename = request.POST.getlist('phile[]')[i]
                # create our DSpace manager
                manager = Manager()
                # remove existing file if it exists so we can replace it
                # with the current upload
                s =  Search()
                jason = s.file("{}.pdf".format(filename), TITLE_ALT)
                if jason and jason[0].get("id"):
                    uri="items/{}/".format(jason[0].get("id"))
                    response = manager.request(
                        uri, "delete"
                    )
                phile = handle_uploaded_file(
                    syllabus, sendero, filename
                )
                if phile:
                    upload = "{}/{}".format(sendero, phile)
                    # verify file type is PDF
                    if magic.from_file(upload, mime=True) == "application/pdf":
                        # create a new parent item that will contain
                        # the uploaded file
                        item = {
                            "course_number": crs_no,
                            "title": crs_title,
                            "title_alt": phile,
                            "year": YEAR,
                            "term": SESS,
                            "user": request.user
                        }
                        new_item = create_item(item)
                        # send file to DSpace
                        #new_file = send_file(new_item, upload)
                        uri="items/{}/bitstreams/".format(new_item["id"])
                        response = manager.request(
                            uri, "post", phile, phile=upload
                        )
                        messages.add_message(
                            request, messages.SUCCESS,
                            'The file was uploaded successfully.',
                            extra_tags='success'
                        )
                    else:
                        messages.add_message(
                            request, messages.ERROR,
                            '''
                                Files must be in PDF format. Please convert
                                your file to PDF and try again.
                            ''',
                            extra_tags='danger'
                        )
                else:
                    messages.add_message(
                        request, messages.ERROR,
                        '''
                            Something has gone awry with the upload.
                            Please try again.
                        ''',
                        extra_tags='danger'
                    )

    return render_to_response(
        "home.html", {
            "depts":dept_list,"courses":secciones,"department":dept,
            "faculty_name":faculty_name,"fid":fid,"year":YEAR,
            "sess":TERM_LIST[SESS],"phile":phile,"dean_chair":dean_chair,
            "division":{"name":division_name,"code":division_code},
            "admin":admin
        },
        context_instance=RequestContext(request)
    )


@portal_auth_required(
    session_var="DSPILOBUS_AUTH", redirect_url=reverse_lazy("access_denied")
)
@csrf_exempt
def dspace_file_search(request):
    if request.method == "POST":
        phile = request.POST.get("phile")
        name = request.POST.get("name")

        jason = []
        content = ""
        if name.strip() != "Staff":
            s =  Search()
            jason = s.file(phile, TITLE_ALT)
        if jason and jason[0].get("name"):
            earl = "{}/bitstream/handle/{}/{}?sequence=1&isAllowed=y".format(
                settings.DSPACE_URL, jason[0].get("handle"), phile
            )
            response = render_to_response(
                "view_file.ajax.html", {"earl":earl},
                context_instance=RequestContext(request)
            )
        else:
            response = HttpResponse(
                "", content_type="text/plain; charset=utf-8"
            )
    else:
        response = HttpResponseRedirect(reverse_lazy("access_denied"))

    return response


@portal_auth_required(
    session_var="DSPILOBUS_AUTH", redirect_url=reverse_lazy("access_denied")
)
def download(request, division, department=""):
    response = HttpResponse(content_type='application/x-gzip')
    name = "{}_{}_syllabi".format(division, department)
    response['Content-Disposition'] = 'attachment; filename={}.tar.gz'.format(
        name
    )
    tar_ball = tarfile.open(fileobj=response, mode='w:gz')
    directory = "{}{}/{}/{}/{}".format(
        settings.UPLOADS_DIR,YEAR,SESS,division,department
    )
    if os.path.isdir(directory):
        tar_ball.add(directory, arcname=name)
        tar_ball.close()
        return response
    else:
        messages.add_message(
            request, messages.ERROR,
            '''
                Currently, there are no course syllabi for
                that department
            ''',
            extra_tags='danger'
        )
        return HttpResponseRedirect(reverse_lazy("home"))
