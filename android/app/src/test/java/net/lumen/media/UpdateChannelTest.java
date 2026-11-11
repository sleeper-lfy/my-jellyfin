package net.lumen.media;

import android.content.Intent;
import android.view.View;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.annotation.Config;
import java.io.IOException;
import java.lang.reflect.Field;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import static org.junit.Assert.*;
import static org.robolectric.Shadows.shadowOf;

@RunWith(RobolectricTestRunner.class) @Config(sdk=33)
public class UpdateChannelTest {
    private GitHubUpdates.Candidate candidate(String url)throws Exception{
        return new GitHubUpdates.Candidate("0.4.21",40,url,5,"a".repeat(64),"","test");
    }
    @Test public void releasesLinkUsesTheExactAttachmentTagAndNeverAnApiOrTargetAddress()throws Exception{
        assertEquals(GitHubUpdates.RELEASES,GitHubUpdates.releasePage(null));
        assertEquals(GitHubUpdates.RELEASES+"/tag/v0.4.21",GitHubUpdates.releasePage(candidate(GitHubUpdates.RELEASES+"/download/v0.4.21/Lumen-android-debug.apk?download=1")));
        assertEquals(GitHubUpdates.RELEASES+"/tag/v0.4.21-preview.1",GitHubUpdates.releasePage(candidate(GitHubUpdates.RELEASES+"/download/v0.4.21-preview.1/Lumen-android-debug.apk")));
        assertEquals(GitHubUpdates.RELEASES,GitHubUpdates.releasePage(candidate(GitHubUpdates.TARGET+"Lumen-android-debug.apk")));
        assertEquals(GitHubUpdates.RELEASES,GitHubUpdates.releasePage(candidate("https://github.com/other/project/releases/download/v0.4.21/app.apk")));
    }
    @Test public void wholeChannelRowOpensTheBrowserBeforeAndAfterAnUpdateIsKnown()throws Exception{
        CountDownLatch release=new CountDownLatch(1);
        try(ActivityController<UpdateActivity> lifecycle=Robolectric.buildActivity(UpdateActivity.class)){
            UpdateActivity activity=lifecycle.get();activity.fetcher=(url,limit)->{release.await(5,TimeUnit.SECONDS);throw new IOException("isolated offline fixture");};
            lifecycle.create().start().resume().visible();View row=activity.getWindow().getDecorView().findViewWithTag("updateChannel");
            assertNotNull(row);assertTrue(row.isFocusable());assertTrue(row.isClickable());assertTrue(row.getMinimumHeight()>=Math.round(48*activity.getResources().getDisplayMetrics().density));
            assertTrue(row.getContentDescription().toString().contains("GitHub Releases"));row.performClick();
            Intent first=shadowOf(activity).getNextStartedActivity();assertEquals(Intent.ACTION_VIEW,first.getAction());assertEquals(GitHubUpdates.RELEASES,first.getDataString());assertTrue(first.hasCategory(Intent.CATEGORY_BROWSABLE));assertNull(first.getType());
            Field field=UpdateActivity.class.getDeclaredField("candidate");field.setAccessible(true);field.set(activity,candidate(GitHubUpdates.RELEASES+"/download/v0.4.21/Lumen-android-debug.apk"));
            row.performClick();Intent selected=shadowOf(activity).getNextStartedActivity();assertEquals(GitHubUpdates.RELEASES+"/tag/v0.4.21",selected.getDataString());
        }finally{release.countDown();}
    }
}
