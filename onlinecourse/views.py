from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.models import User
from .models import Course, Enrollment, Question, Choice, Submission
import logging

logger = logging.getLogger(__name__)


def registration_request(request):
    context = {}
    if request.method == "GET":
        return render(request, "onlinecourse/user_registration_bootstrap.html", context)

    username = request.POST["username"]
    password = request.POST["psw"]
    first_name = request.POST["firstname"]
    last_name = request.POST["lastname"]

    if User.objects.filter(username=username).exists():
        context["message"] = "User already exists."
        return render(request, "onlinecourse/user_registration_bootstrap.html", context)

    user = User.objects.create_user(
        username=username,
        first_name=first_name,
        last_name=last_name,
        password=password,
    )
    login(request, user)
    return redirect("onlinecourse:index")


def login_request(request):
    context = {}
    if request.method == "POST":
        user = authenticate(
            username=request.POST["username"],
            password=request.POST["psw"],
        )
        if user is not None:
            login(request, user)
            return redirect("onlinecourse:index")
        context["message"] = "Invalid username or password."
    return render(request, "onlinecourse/user_login_bootstrap.html", context)


def logout_request(request):
    logout(request)
    return redirect("onlinecourse:index")


def check_if_enrolled(user, course):
    return (
        user.is_authenticated
        and Enrollment.objects.filter(user=user, course=course).exists()
    )


class CourseListView(generic.ListView):
    template_name = "onlinecourse/course_list_bootstrap.html"
    context_object_name = "course_list"

    def get_queryset(self):
        courses = Course.objects.order_by("-total_enrollment")[:10]
        for course in courses:
            course.is_enrolled = check_if_enrolled(self.request.user, course)
        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = "onlinecourse/course_details_bootstrap.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        course = context["course"]
        course.is_enrolled = check_if_enrolled(self.request.user, course)
        return context


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if request.user.is_authenticated and not check_if_enrolled(request.user, course):
        Enrollment.objects.create(user=request.user, course=course, mode="honor")
        course.total_enrollment += 1
        course.save()
    return HttpResponseRedirect(
        reverse("onlinecourse:course_details", args=(course.id,))
    )


def extract_answers(request):
    selected_ids = []
    for key in request.POST:
        if key.startswith("choice"):
            for value in request.POST.getlist(key):
                try:
                    selected_ids.append(int(value))
                except (TypeError, ValueError):
                    continue
    return selected_ids


def submit(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    if not request.user.is_authenticated:
        return redirect("onlinecourse:login")

    enrollment = get_object_or_404(
        Enrollment, user=request.user, course=course
    )
    submission = Submission.objects.create(enrollment=enrollment)
    selected_ids = extract_answers(request)

    valid_choices = Choice.objects.filter(
        question__course=course, id__in=selected_ids
    )
    submission.choices.set(valid_choices)

    return HttpResponseRedirect(
        reverse(
            "onlinecourse:show_exam_result",
            args=(course_id, submission.id),
        )
    )


def show_exam_result(request, course_id, submission_id):
    course = get_object_or_404(Course, pk=course_id)
    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__course=course,
        enrollment__user=request.user,
    )
    selected_ids = list(submission.choices.values_list("id", flat=True))

    grade = 0
    max_score = 0
    question_results = []
    for question in course.question_set.all():
        max_score += question.grade
        choices = question.choice_set.all()
        selected_for_question = choices.filter(id__in=selected_ids)
        correct = question.is_get_score(selected_ids)
        if correct:
            grade += question.grade
        question_results.append({
            "question": question,
            "choices": choices,
            "selected_choices": selected_for_question,
            "is_correct": correct,
        })

    percentage = round(grade * 100 / max_score) if max_score else 0
    context = {
        "course": course,
        "submission": submission,
        "grade": grade,
        "max_score": max_score,
        "percentage": percentage,
        "question_results": question_results,
    }
    return render(request, "onlinecourse/exam_result_bootstrap.html", context)
