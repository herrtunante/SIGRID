<?php
echo "<p><b>All SIGRID grid files in this folder</br></b><p>";
$i=1;

$files = array();
$dir = opendir('.'); // open the cwd..also do an err check.
while(false != ($file = readdir($dir))) {
        if(($file != ".") and ($file != "..") and ($file != "index.php")) {
                $files[] = $file; // put in array.
        }   
}

natsort($files); // sort.

// print.
foreach($files as $file) {
        echo("$i <a href='$file'>$file</a> <br />\n");
		$i++;
}

closedir($dh);
?>