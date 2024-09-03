import os
from django.shortcuts import render, redirect
from django.db.models import Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth import login, logout
from django.contrib.auth import views as auth_views
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .decorators import *
from .forms import *


@login_required(login_url='core:login')
def index(request):
    user = request.user
    context = {}
    preference, _ = NotificationSetting.objects.get_or_create(user=user.profile)
    threads = Thread.objects.filter(Q(user1=user.profile) | Q(user2=user.profile))
    people = Profile.objects.exclude(user=user)
    groups = Group.objects.filter(members=user)
    first_letters = sorted(set(person.user.username[0].upper() for person in people))
    images_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp']
          
    if request.method == 'POST':
        if 'change-avatar' in request.POST:
            uploaded_file = request.FILES.get('avatar')
            print(uploaded_file)
            if uploaded_file:
                profile = request.user.profile
                profile.avatar = uploaded_file
                profile.save()
            return redirect('core:home')

        elif 'profile-form' in request.POST:
            profile_form = UserAndProfileForm(request.POST, instance=user)
            if profile_form.is_valid():
                user.first_name = profile_form.cleaned_data['first_name']
                user.last_name = profile_form.cleaned_data['last_name']
                user.email = profile_form.cleaned_data['email']
                
                user.profile.country = profile_form.cleaned_data['country']
                user.profile.phone = profile_form.cleaned_data['phone']
                user.profile.bio = profile_form.cleaned_data['bio']
                user.save()
                user.profile.save()
                return redirect('core:home')
            
        elif 'create_group' in request.POST:
            group_form = GroupForm(request.POST, request.FILES)
            if group_form.is_valid():
                group = Group.objects.create(owner=user.profile, avatar=group_form.cleaned_data['avatar'], name=group_form.cleaned_data['name'], description=group_form.cleaned_data['description'])
                for member in group_form.cleaned_data['members']:
                    group.members.add(member, user)
                messages.success(request, "Group created successfully!.")
                return redirect('core:home')

        elif 'social-form' in request.POST:
            socials_form = SocialsForm(request.POST, instance=user.profile.social)
            if socials_form.is_valid():
                social_data = socials_form.save(commit=False)
                social_data.user = user.profile
                social_data.save()
                return redirect('core:home')
            
        elif 'change-password' in request.POST:
            password_form = PasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                password_form.save()
                return redirect('core:home')
            
        elif 'notif-form' in request.POST:
            notif_form = NotificationPreferenceForm(request.POST, instance=preference)
            if notif_form.is_valid():
                notif_form.save()
                return redirect('core:home')
        
        elif 'delete-chat' in request.POST:
            thread_id = request.POST.get('thread-id')
            thread = Thread.objects.get(id=thread_id)
            if thread.messages.all():
                for message_id in thread.messages.all():
                    message = Message.objects.get(id=message_id.id)
                    message.is_deleted_by_sender = True
                    message.save()
            return redirect('core:home')

        elif 'add_member_submit' in request.POST:
            group_id = request.POST.get('group_id')
            group = Group.objects.get(id=group_id)
            for member in request.POST.get('selected_users'):
                group.members.add(member)
                group.save()

        elif any(key.startswith('files[') for key in request.FILES):
            uploaded_files = [f for key, f in request.FILES.items() if key.startswith('files[')]
            action = request.POST.get('action')
            reply_to = request.POST.get('replyTo')
            message_content = request.POST.get('message', None)
            group_id = request.POST.get('groupId', None)
            thread_id = request.POST.get('threadId', None)
            sender_id = request.POST.get('senderId', None)
            receiver_id = request.POST.get('receiverId', None)
            group = None
            if receiver_id:
                try:
                    receiver_profile = Profile.objects.get(user__id=receiver_id)
                except Profile.DoesNotExist as e:
                    receiver_profile = None
                    print(e)

            if sender_id:
                try:
                    sender_profile = Profile.objects.get(user__id=sender_id)
                    sender_avatar = sender_profile.avatar.url if sender_profile.avatar else None
                except Profile.DoesNotExist as e:
                    sender_profile = None
                    print(e)

            if group_id:
                try:
                    group = Group.objects.get(id=group_id)
                except Group.DoesNotExist as e:
                    group = None
                    print(e)


            channel_layer = get_channel_layer()
            global channel_name
            global channel_type

            
            if message_content:
                channel_type = 'handle_upload_with_message'
            else:
                channel_type = 'handle_file_upload'

            if action == 'reply_file':
                message_reply = Message.objects.get(id=reply_to)
                global reply_content

                if message_reply.content != None:
                    reply_content = message_reply.content
                else:
                    reply_content = message_reply.file_message.name

                if group:
                    message = Message.objects.create(sender=sender_profile, content=message_content, reply=message_reply, group=group)
                    channel_name = f'group_{group_id}'
                else:
                    if thread_id:                   
                        thread = Thread.objects.get(id=thread_id)
                        message = Message.objects.create(thread=thread, sender=sender_profile, receiver=receiver_profile, content=message_content, reply=message_reply)
                        channel_name = f'chat_{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}'
                    else:
                        print(thread_id)
                
                file_names = []
                file_urls = []
                file_sizes = []
                global rfile_extension
                for f in uploaded_files:
                    rfile_extension = os.path.splitext(f.name)[1]
                    if rfile_extension in images_extensions:
                        uploaded_file = Files.objects.create(image_path=f, name=f.name, message=message)
                        file_names.append(f.name)
                        file_urls.append(uploaded_file.image_path.url)
                        file_sizes.append(os.path.getsize(uploaded_file.image_path.path))

                    else:
                        uploaded_file = Files.objects.create(file_path=f, name=f.name, message=message)
                        file_names.append(f.name)
                        file_urls.append(uploaded_file.file_path.url)
                        file_sizes.append(os.path.getsize(uploaded_file.file_path.path))

                async_to_sync(channel_layer.group_send)(
                    channel_name,
                    {
                        'type': channel_type,
                        'reply_id': message_reply.id,
                        'sub_action': 'reply_file',
                        'reply_message': reply_content,
                        'message_id': message.id,
                        'message': message,
                        'sender_id': sender_id,
                        'sender_avatar': sender_avatar,
                        'timestamp': message.timestamp.strftime('%I:%M %p'),
                        'files_name': file_names,
                        'file_extensions': rfile_extension,
                        'file_sizes': file_sizes,
                        'file_urls': file_urls,
                    })
                print(f"Message successfully sent to channel: {channel_name}")
            else: 
                if group:
                    message = Message.objects.create(sender=sender_profile, content=message_content, group=group)
                    channel_name = f'group_{group_id}'
                else:
                    if thread_id:
                        print('Action: upload file thread_id:', thread_id)
                   
                        thread = Thread.objects.get(id=thread_id)
                        message = Message.objects.create(thread=thread, sender=sender_profile, receiver=receiver_profile, content=message_content)
                        channel_name = f'chat_{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}'


                file_names = []
                file_urls = []
                file_sizes = []
                global file_extension
                for f in uploaded_files:
                    file_extension = os.path.splitext(f.name)[1]
                    if file_extension in images_extensions:
                        uploaded_file = Files.objects.create(image_path=f, name=f.name, message=message)
                        file_names.append(f.name)
                        file_urls.append(uploaded_file.image_path.url)
                        file_sizes.append(os.path.getsize(uploaded_file.image_path.path))

                    else:
                        uploaded_file = Files.objects.create(file_path=f, name=f.name, message=message)
                        file_names.append(f.name)
                        file_urls.append(uploaded_file.file_path.url)
                        file_sizes.append(os.path.getsize(uploaded_file.file_path.path))

                async_to_sync(channel_layer.group_send)(
                    channel_name,
                    {
                        'type': channel_type,
                        'sub_action': 'reply_file',
                        'reply_message': message_content,
                        'message_id': message.id,
                        'message': message,
                        'sender_id': sender_id,
                        'sender_avatar': sender_avatar,
                        'timestamp': message.timestamp.strftime('%I:%M %p'),
                        'files_name': file_names,
                        'file_extensions': file_extension,
                        'file_sizes': file_sizes,
                        'file_urls': file_urls,
                    })
                print(f"Message successfully sent to channel: {channel_name}")

    
    group_list = []
    person_list = []

    for group in groups:
        group_list.append(group)

    for person in people:
        person_list.append(person)
    
    profile_form = UserAndProfileForm(instance=user)
    group_form = GroupForm()
    socials_form = SocialsForm(instance=user.profile.social or None)
    password_form = PasswordChangeForm(request.user)
    notifications_form = NotificationPreferenceForm(instance=preference)
    context.update({
        'all_chats': len(group_list + person_list),
        'people': people,
        'groups': groups,
        'first_letters': first_letters,
        'threads': threads,
        'profile_form': profile_form,
        'group_form': group_form,
        'socials_form': socials_form,
        'password_form': password_form,
        'notifications_form': notifications_form,
    })
    5
    return render(request, 'index.html', context)

@login_required(login_url='core:login')
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('core:home')

@anonymous_required
def register_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = form.cleaned_data.get('email')
            user.set_password(form.cleaned_data.get('password1'))
            user.save()
            login(request, user)
            return redirect('core:home')
    else:
        form = CustomUserCreationForm()
    
    return render(request, 'signup.html', {'registration_form': form})


class CustomPasswordResetView(auth_views.PasswordResetView):

    template_name = 'custom-password-reset.html'
    email_template_name = 'custom-password-reset-email.html'
    success_url = None

    def form_valid(self, form):
        super().form_valid(form)
        return render(self.request, self.template_name, {'form': form, 'reset_email_sent': True})

    def get_success_url(self):
        return self.request.path_info