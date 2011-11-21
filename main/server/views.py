"""
Biostar views
"""
from main.server import html, models, const, formdef
from main.server.html import get_page

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.paginator import Paginator, InvalidPage, EmptyPage
from django.contrib.auth import authenticate, login, logout
from django.conf import settings
from django.http import HttpResponse
from django.db.models import Q

# the openid association model
from django_openid_auth.models import UserOpenID

# import all constants
from main.server.const import *

def get_questions():
    "Returns a common queryset that can be used to select questions"
    #return models.Question.objects.select_related('post', 'post__author','post__author__profile')
    return models.Post.objects.filter(post_type=POST_QUESTION).select_related('author','author__profile')

def index(request):
    "Main page"
    
    # eventually we will need to order by relevance
    qs = get_questions()
    qs = qs.order_by('-touch_date')
    page  = get_page(request, qs, per_page=20)
    return html.template( request, name='index.html', page=page)

def user_profile(request, uid):
    "User's profile page"
    user = models.User.objects.get(id=uid)
    profile = models.UserProfile.objects.get(user=user)
    questions = models.Post.objects.filter(author=user, post_type=POST_QUESTION).select_related('author','author__profile')
    answers   = models.Post.objects.filter(author=user, post_type=POST_ANSWER).select_related('author', 'author_profile', 'parent__author','parent__author__profile')

    return html.template(request, name='user.profile.html',
        user=request.user, profile=profile, selected=user,
        questions=questions.order_by('-score'),
        answers=answers.order_by('-score'))

def user_list(request):
    search  = request.GET.get('search','')[:80] # trim for sanity
    if search:
        query = Q(first_name__icontains=search) | Q(last_name__icontains=search)
        users = models.User.objects.filter(query).select_related('profile').order_by("-profile__score")
    else:
        users = models.User.objects.select_related('profile').order_by("-profile__score")
    page  = get_page(request, users, per_page=35)
    return html.template(request, name='user.list.html', page=page, rows=7, search=search)

def tag_list(request):
    tags = models.Tag.objects.all().order_by('-count')
    page = get_page(request, tags, per_page=50)
    return html.template(request, name='tag.list.html', page=page)

def badge_list(request):
    badges = models.Badge.objects.filter(secret=False).order_by('name')
    return html.template(request, name='badge.list.html', badges=badges)

def search(request):
    return html.template(request, name='todo.html')

def question_list(request):
    "Lists all the questions" 
    qs = get_questions().filter(answer_count=0)
    page = get_page(request, qs) 
    return html.template(request, name='question.list.html', page=page)

def question_tagged(request, tag_name):
    qs = get_questions().filter(post__tag_set__name=tag_name)
    page = get_page(request, qs) 
    return html.template(request, name='question.list.html', page=page)

def question_unanswered(request):
    qs = get_questions().filter(answer_count=0)
    page = get_page(request, qs) 
    return html.template(request, name='question.list.html', page=page)
    
def post_show(request, pid):
    "Returns a question with all answers"
    
    qs = models.Post.objects
    question = qs.filter(post_type=POST_QUESTION).select_related('children', 'votes').get(id=pid)
    
    if request.user.is_authenticated():
        question.views += 1
        question.save()
        
    #qs = models.Post.all_objects if 'view_deleted' in request.permissions else models.Post.objects
    answers = models.Post.answers.filter(parent=question)
    answers = answers.order_by('-answer_accepted','-score')
    
    return html.template( request, name='post.show.html', question=question, answers=answers )

def form_revision(post, form):
    "Creates a revision from a form post"
    # sanity check
    assert form.is_valid(), 'form is not valid'
    title   = form.cleaned_data.get('title','')
    content = form.cleaned_data.get('content', '')
    tags    = form.cleaned_data.get('tags', '')
    tag_string = html.tag_strip(tags)    
    post.create_revision(content=content, tag_string=tag_string, title=title)

def show_post(pid, slug='title', anchor=None):
    if anchor:
        url = '/post/show/%s/%s/#%s' % (pid, slug, anchor)
    else:
        url = '/post/show/%s/%s/' % (pid, slug)
    
    return html.redirect(url)
    
@login_required(redirect_field_name='/openid/login/')
def answer_edit(request, pid=0):
    return post_edit(request=request, pid=pid, ptype=POST_ANSWER)
    
@login_required(redirect_field_name='/openid/login/')
def post_edit(request, pid=0, ptype=POST_QUESTION):
    """
    Handles parent post related tasks
    """
    
    newpost   = (pid == 0)
    form_data = (request.method == 'POST')
    params    = html.Params()
    
    # get post_type 
    assert ptype in POST_REV_MAP, 'Invalid post_type %s' % ptype
    
    # select the right type of form
    if ptype == POST_QUESTION:
        factory = formdef.PostForm
    else:
        factory = formdef.ContentForm
    
    # we have incoming form data for posts with no parents
    if form_data:
        form = factory(request.POST)
        if not form.is_valid():
            return html.template( request, name='edit.post.html', form=form, params=params)
        if newpost:
            with transaction.commit_on_success():
                post = models.Post.objects.create(author=request.user, post_type=ptype)
                form_revision(post=post, form=form)
        else:
            post = models.Post.objects.get(pk=pid)
            post.authorize(request)
            form_revision(post=post, form=form)
        
        # redirect to parent if exists
        if post.parent:
            return show_post(post.parent.id, post.parent.slug, post.id)
        else:
            return show_post(post.id, post.slug)
    
    # there is no incomig data render the forms
    else:
        if newpost:
            form = factory()
        else:
            post = models.Post.objects.get(pk=pid)
            post.authorize(request)            
            form = factory(initial=dict(title=post.title, content=post.content, tags=post.tag_string))
        return html.template( request, name='edit.post.html', form=form, params=params)
        

@login_required(redirect_field_name='/openid/login/')
def post_content(request, pid=0):
    "Handles actions for posts that only contain content (answers/comments)"

    newpost   = (pid == 0)
    form_data = (request.method == 'POST')
    
    # get post_type 
    post_type = int(request.REQUEST.get('post_type', POST_ANSWER))
    assert post_type in POST_REV_MAP, 'Invalid post_type %s' % post_type
    
    # get the parent post
    post = models.Post.objects.get(pk=pid)
    
    # we have incoming form data for posts with no parents
    if form_data:
        form = formdef.ContentForm(request.POST)
        if not form.is_valid():
            return show_post(post.id, post.slug, 'post-answer')
        
        with transaction.commit_on_success():
            content = models.Post.objects.create(author=request.user, post_type=post_type, parent=post)
            form_revision(post=content, form=form) 
        
        return show_post(post.id, post.slug, content.id)
        
    return show_post(post.id, post.slug)
    
        
def revision_list(request, pid):
    post = models.Post.objects.get(pk=pid)
    revisions = list(post.revisions.order_by('date')) # Oldest first, will need to be reversed later
    
    # We need to annotate the revisions with exactly what was changed
    # 'verb' is a word for the action box to describe the revision
    # 'modified' is a list (title, content, tag_string) of boolean values for if it was changed
    def revision_data(rev):
        return rev.title, rev.content, rev.tag_string
    last_data = revision_data(revisions[0])
    revisions[0].verb = 'created'
    revisions[0].modified = [True, True, True] # Always display the first revision
    for revision in revisions[1:]:
        if revision.action:
            revision.verb = 'performed'
        else:
            revision.verb = 'edited'
            data = revision_data(revision)
            revision.modified = [current != last for current, last in zip(data, last_data)]
            last_data = data
    revisions.reverse()
    
    return html.template(request, name='revision.list.html', revisions=revisions, post=post)
   
@login_required(redirect_field_name='/openid/login/')
def comment_add(request, pid):
    
    parent  = models.Post.objects.get(pk=pid)
    content = request.POST['text']
    comment = models.Post(author=request.user, content=content, parent=parent, post_type=POST_COMMENT)
    comment.save()
    if parent.post_type == POST_ANSWER:
        parent = parent.parent
    return show_post(pid=parent.id, slug=parent.slug, anchor=comment.id)
    
def vote(request):
    "Handles all voting on posts"
    if request.method == 'POST':
        
        author = request.user
        if not author.is_authenticated():
            return html.json_response({'status':'error', 'msg':'You must be logged in to vote'})
        
        post_id = int(request.POST.get('post'))
        post = models.Post.objects.get(id=post_id)
        
        if post.author == author:
            return html.json_response({'status':'error', 'msg':'You cannot vote on your own post'})
        
        type = int(request.POST.get('type'))
        
        old_vote = post.get_vote(author, type)
        if old_vote:
            old_vote.delete()
            return html.json_response({
                'status':'success',
                'msg':'%s removed' % old_vote.get_type_display()})
        else:
            vote = post.add_vote(author, type)
            if type in models.OPPOSING_VOTES: 
                # Remove an opposing vote if it exists
                post.remove_vote(author, models.OPPOSING_VOTES[type])
            return html.json_response({
                'status':'success',
                'msg':'%s added' % vote.get_type_display()})
                    

    return html.json_response({'status':'error', 'msg':'POST method must be used'})

def moderate(request):
    if request.method == 'POST':
        author = request.user
        if 'moderate_post' not in request.permissions: # Need to also check for actual mod permissions
            return html.json_response({'status':'error', 'msg':'You do not have permission to moderate posts.'})        

        post_id = int(request.POST.get('post'))
        post = models.Post.objects.get(id=post_id)
        
        action = request.POST.get('action')
        action_map = {'close':models.REV_CLOSE, 'reopen':models.REV_REOPEN,
                      'delete':models.REV_DELETE, 'undelete':models.REV_UNDELETE}
        post.moderator_action(action_map[action], author)
        
        return html.json_response({'status':'success', 'msg':'%s performed' % action})
        
    return html.json_response({'status':'error', 'msg':'POST method must be used'})
        


@login_required(redirect_field_name='/openid/login/')
def preview(request):
    "This runs the markdown preview functionality"
    content = request.POST.get('content','no input')

    try:
        output = html.generate(content)
    except KeyError, exc:
        # return more userfriendly errors, used for debugging
        output = 'Error: %s' % str(exc)

    return HttpResponse(output, mimetype='text/plain')
